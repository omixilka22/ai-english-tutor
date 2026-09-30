"""A one-off lesson for an existing student, independent of weekly schedules."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from aiogram import F,Router
from aiogram.fsm.state import State,StatesGroup
from sqlalchemy.exc import SQLAlchemyError
from app.bot.ui import clear_flow,show_screen,keyboard,navigation
from app.database.database import AsyncSessionLocal
from app.services.calendar_service import CalendarService,utcnow
from app.services.recurrence import local_instant
from app.services.user_service import UserService

router=Router(name='extra_lesson')
TIMEZONE='Europe/Kyiv'


class ExtraLesson(StatesGroup):
    date=State()
    duration=State()
    confirm=State()


async def render(event,state,error=''):
    data=await state.get_data()
    current=await state.get_state()
    header=f"＋ Додаткове заняття · {data['student_name']}\n\n"
    rows=[]
    if current==ExtraLesson.date.state:
        example=(utcnow().astimezone(ZoneInfo(TIMEZONE))+timedelta(days=1)).strftime('%d.%m.%Y')+' 18:30'
        text=f'Крок 1 / 3 · Дата і час\n{TIMEZONE}\n\nВведіть ДД.ММ.РРРР ГГ:ХХ, наприклад {example}.'
        back=f"student_lessons_{data['student_id']}"
    else:
        moment=datetime.fromisoformat(data['scheduled_at']).astimezone(ZoneInfo(TIMEZONE))
        if current==ExtraLesson.duration.state:
            text=f'Крок 2 / 3 · Тривалість\n\n{moment:%d.%m.%Y %H:%M} · {TIMEZONE}\nОберіть або введіть тривалість у хвилинах (1–1440).'
            rows=[[(f'{n} хв',f'extra_duration_{n}') for n in (30,45,60)],[(f'{n} хв',f'extra_duration_{n}') for n in (90,120)]]
        else:
            text=(f"Крок 3 / 3 · Підтвердження\n\n{moment:%d.%m.%Y %H:%M} · {TIMEZONE}\n"
                  f"Тривалість: {data['duration_minutes']} хв\n\nЛише одне заняття, без повторення. Щотижневий розклад не зміниться.")
            rows=[[('✓ Додати заняття','extra_confirm')]]
        back='extra_back'
    rows += [[('‹ Назад',back),('Скасувати',f"student_lessons_{data['student_id']}")],[('⌂ Головне меню','home')]]
    await show_screen(event,state,header+text+ ('\n\n'+error if error else ''),reply_markup=keyboard(rows))


@router.callback_query(F.data.regexp(r'^extra_lesson_\d+$'))
async def begin(callback,state):
    student_id=int(callback.data.rsplit('_',1)[1])
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            student,_=await CalendarService.student_access(session,callback.from_user.id,student_id,write=True)
        except ValueError as error:
            await show_screen(callback,state,str(error))
            return
        user=await UserService.get_by_id(session,student.user_id)
    await clear_flow(state)
    await state.update_data(student_id=student_id,student_name=user.name if user else 'Учень')
    await state.set_state(ExtraLesson.date)
    await render(callback,state)


@router.message(ExtraLesson.date)
async def enter_date(message,state):
    try:
        naive=datetime.strptime(message.text or '', '%d.%m.%Y %H:%M')
        instant=local_instant(naive.date(),naive.time(),TIMEZONE,strict=True)
        if instant<=utcnow():
            raise ValueError()
    except ValueError:
        await render(message,state,'Вкажіть майбутню дату й коректний місцевий час у форматі ДД.ММ.РРРР ГГ:ХХ.')
        return
    await state.update_data(scheduled_at=instant.isoformat())
    await state.set_state(ExtraLesson.duration)
    await render(message,state)


async def set_duration(event,state,raw):
    if len(raw)>4 or not raw.isascii() or not raw.isdigit() or not 1<=int(raw)<=1440:
        await render(event,state,'Введіть цілу кількість хвилин від 1 до 1440.')
        return
    await state.update_data(duration_minutes=int(raw))
    await state.set_state(ExtraLesson.confirm)
    await render(event,state)


@router.message(ExtraLesson.duration)
async def enter_duration(message,state):
    await set_duration(message,state,(message.text or '').strip())


@router.callback_query(ExtraLesson.duration,F.data.regexp(r'^extra_duration_(30|45|60|90|120)$'))
async def choose_duration(callback,state):
    await callback.answer()
    await set_duration(callback,state,callback.data.rsplit('_',1)[1])


@router.callback_query(ExtraLesson.confirm,F.data=='extra_back')
@router.callback_query(ExtraLesson.duration,F.data=='extra_back')
async def back(callback,state):
    await state.set_state(ExtraLesson.duration if await state.get_state()==ExtraLesson.confirm.state else ExtraLesson.date)
    await callback.answer()
    await render(callback,state)


@router.callback_query(ExtraLesson.confirm,F.data=='extra_confirm')
async def confirm(callback,state):
    data=await state.get_data()
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            lesson=await CalendarService.create_extra(session,callback.from_user.id,data['student_id'],
                scheduled_at=datetime.fromisoformat(data['scheduled_at']),duration_minutes=data['duration_minutes'],timezone_name=TIMEZONE)
        except ValueError as error:
            await session.rollback()
            await render(callback,state,str(error))
            return
        except SQLAlchemyError:
            await session.rollback()
            await render(callback,state,'Не вдалося зберегти заняття. Спробуйте ще раз.')
            return
    await clear_flow(state)
    await show_screen(callback,state,'✓ Додаткове заняття створено. Щотижневий розклад залишився без змін.',
        reply_markup=keyboard([[('📚 Відкрити заняття',f'lesson_{lesson.id}')],[('‹ До занять',f"student_lessons_{data['student_id']}"),('⌂ Головне меню','home')]]))


@router.callback_query(F.data.startswith('extra_duration_') | F.data.in_({'extra_confirm','extra_back'}))
async def stale(callback):
    await callback.answer('Цю дію вже завершено. Відкрийте меню учня знову.',show_alert=True)
