"""Explicit capture and speaker confirmation inside a lesson card."""
import re
from aiogram import Router, F
from sqlalchemy import select
from app.bot.ui import show_screen, clear_flow, keyboard
from app.database.database import AsyncSessionLocal
from app.database.models import Transcript
from app.services.calendar_service import CalendarService
from app.services import recall_service

router=Router(name='recall')
LABELS={'queued':'Запуск у черзі','creating':'Запит на підключення надіслано',
    'create_unknown':'Потрібно перевірити підключення в Recall; повторний запуск заблоковано',
    'joining':'Помічник підключається — впустіть його в Google Meet',
    'recording':'Триває запис розмови','ended':'Зустріч завершена, чекаємо запис',
    'recorded':'Запис готовий, очікує транскрибації','transcribing':'Recall розпізнає розмову',
    'transcribe_unknown':'Очікуємо підтвердження запиту на транскрибацію від Recall',
    'download':'Завантажуємо готовий текст','ready_roles':'Текст отримано — уточніть ролі',
    'ready':'Текст готовий. Аналіз запуститься після підтвердження проведення уроку',
    'analysis':'Текст передано в процес аналізу','failed':'Транскрибація потребує перевірки',
    'cancelled':'Запуск скасовано','cleaned':'Транскрипт видалено; підтверджені матеріали залишилися'}
SPEAKER=re.compile(r'^\[\d+:\d+\] Учасник ([^ ]+) \(([^\n]*)\): ',re.M)


def speakers(text):
    return dict(SPEAKER.findall(text))


def assign_roles(text, teacher_id):
    found=speakers(text)
    if len(found)!=2 or teacher_id not in found:
        raise ValueError('Потрібні рівно два розпізнані учасники. Можна аналізувати без визначення ролей.')
    return SPEAKER.sub(lambda m: m.group(0).split(']')[0]+'] '+
        ('Teacher' if m.group(1)==teacher_id else 'Student')+': ',text)


async def render(callback,state,note=''):
    lesson_id=int(callback.data.rsplit('_',1)[-1])
    async with AsyncSessionLocal() as db:
        try:
            await CalendarService.lesson_access(db,callback.from_user.id,lesson_id,write=True)
            row=await recall_service.session_for(db,lesson_id)
            transcript=(await db.execute(select(Transcript).where(Transcript.lesson_id==lesson_id))).scalar_one_or_none()
        except ValueError as error:
            await show_screen(callback,state,str(error));return
    rows=[]
    if row is None:
        text='Помічник зайде у Google Meet за посиланням учня. Запис і розпізнавання витрачають баланс Recall. Учасники мають знати про транскрибацію.'
        rows.append([('Почати транскрибацію',f'recall_start_{lesson_id}')])
    else:
        text=LABELS.get(row.state,row.state)
        if row.error: text+='\nКод: '+row.error
        if row.cleanup_state=='pending': text+='\nВидалення у Recall очікує підтвердження.'
        if row.state=='failed' and not row.bot_id and row.error in ('http_400','http_401','http_403','http_429','http_507','not_configured'):
            rows.append([('Повторити після виправлення налаштувань',f'recall_start_{lesson_id}')])
        if row.state=='ready_roles' and transcript:
            choices=speakers(transcript.text)
            if len(choices)==2:
                text+='\n\nХто з цих учасників — викладач? Другий учасник буде позначений як учень.'
                for index,(speaker_id,name) in enumerate(choices.items()):
                    rows.append([(f'Викладач: {name[:60]}',f'recall_role_{index}_{lesson_id}')])
            rows.append([('Аналіз без визначення ролей',f'recall_neutral_{lesson_id}')])
        if row.state in ('queued','creating','create_unknown','joining','recording') and not row.leave_requested:
            rows.append([('Завершити запис',f'recall_stop_{lesson_id}')])
        rows.append([('Оновити стан',f'recall_{lesson_id}')])
    rows.append([('‹ До уроку',f'lesson_{lesson_id}'),('⌂ Головне меню','home')])
    await show_screen(callback,state,'🎙 Транскрибація уроку\n\n'+(note+'\n\n' if note else '')+text,reply_markup=keyboard(rows))


@router.callback_query(F.data.regexp(r'^recall_\d+$'))
async def detail(callback,state):
    await callback.answer();await clear_flow(state)
    await render(callback,state)


@router.callback_query(F.data.regexp(r'^recall_(start|stop|neutral)_\d+$'))
@router.callback_query(F.data.regexp(r'^recall_role_[01]_\d+$'))
async def action(callback,state):
    await callback.answer()
    lesson_id=int(callback.data.rsplit('_',1)[-1]);note=''
    async with AsyncSessionLocal() as db:
        try:
            if callback.data.startswith('recall_start_'):
                await recall_service.start(db,callback.from_user.id,lesson_id)
            elif callback.data.startswith('recall_stop_'):
                await recall_service.stop(db,callback.from_user.id,lesson_id)
            else:
                await CalendarService.lesson_access(db,callback.from_user.id,lesson_id,write=True)
                row=await recall_service.session_for(db,lesson_id)
                if row is None or row.state!='ready_roles': raise ValueError('Ця дія вже виконана або недоступна.')
                transcript=(await db.execute(select(Transcript).where(Transcript.lesson_id==lesson_id))).scalar_one()
                if callback.data.startswith('recall_role_'):
                    index=int(callback.data.split('_')[2])
                    choices=list(speakers(transcript.text))
                    if len(choices)!=2: raise ValueError('Склад учасників змінився. Оновіть екран.')
                    transcript.text=assign_roles(transcript.text,choices[index])
                transcript.source='recall';row.state='ready';row.notice_sent=False
                await db.commit()
        except ValueError as error:
            await db.rollback();note=str(error)
    await render(callback,state,note)
