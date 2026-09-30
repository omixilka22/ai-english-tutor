"""Teacher-managed Meet link in a student's card."""
from aiogram import F, Router
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.exc import SQLAlchemyError
from app.bot.ui import clear_flow, show_screen, keyboard, navigation
from app.database.database import AsyncSessionLocal
from app.services.calendar_service import CalendarService
from app.services.meeting_service import meeting_url, save_meeting_url

router=Router(name='meeting')


class Meeting(StatesGroup):
    url=State()
    remove=State()


@router.callback_query(F.data.regexp(r'^(meet|notification_meet)_\d+$'))
async def show(callback,state):
    await callback.answer()
    await clear_flow(state)
    student_id=int(callback.data.rsplit('_',1)[1])
    async with AsyncSessionLocal() as session:
        try:
            student,_=await CalendarService.student_access(session,callback.from_user.id,student_id,write=True)
        except ValueError as error:
            await show_screen(callback,state,str(error))
            return
        url=meeting_url(student)
    rows=[[('✎ Замінити' if url else '＋ Додати',f'meet_edit_{student_id}')]]
    if url:
        rows.append([('Прибрати посилання',f'meet_remove_{student_id}')])
    rows.append([('‹ До учня',f'student_{student_id}'),('⌂ Головне меню','home')])
    await show_screen(callback,state,'🎥 Посилання на урок\n\n'+(url or 'Ще не додано.')+
        '\n\nОдне посилання для всіх занять цього учня. Учень отримує його за годину, ви — за 15 хвилин до уроку.',reply_markup=keyboard(rows))


@router.callback_query(F.data.regexp(r'^meet_(edit|remove)_\d+$'))
async def begin(callback,state):
    await callback.answer()
    student_id=int(callback.data.rsplit('_',1)[1])
    async with AsyncSessionLocal() as session:
        try:
            await CalendarService.student_access(session,callback.from_user.id,student_id,write=True)
        except ValueError as error:
            await show_screen(callback,state,str(error))
            return
    await clear_flow(state)
    await state.update_data(meeting_student_id=student_id)
    removing=callback.data.startswith('meet_remove_')
    await state.set_state(Meeting.remove if removing else Meeting.url)
    markup=navigation(f'meet_{student_id}')
    if removing:
        markup.inline_keyboard.insert(0,keyboard([[('Так, прибрати','meet_remove_confirm')]]).inline_keyboard[0])
    await show_screen(callback,state,'Прибрати посилання? Наступні нагадування будуть без нього.' if removing else
        'Створіть зустріч у Google Meet та вставте її посилання:\nhttps://meet.google.com/abc-defg-hij\n\nВоно використовуватиметься для всіх занять цього учня.',reply_markup=markup)


async def save(event,state,value):
    data=await state.get_data()
    student_id=data['meeting_student_id']
    async with AsyncSessionLocal() as session:
        try:
            await save_meeting_url(session,event.from_user.id,student_id,value)
        except (ValueError,SQLAlchemyError) as error:
            await session.rollback()
            await show_screen(event,state,str(error) if isinstance(error,ValueError) else 'Не вдалося зберегти. Спробуйте ще раз.',reply_markup=navigation(f'meet_{student_id}'))
            return
    await clear_flow(state)
    await show_screen(event,state,'✓ Посилання збережено.' if value is not None else '✓ Посилання прибрано.',reply_markup=navigation(f'meet_{student_id}'))


@router.message(Meeting.url)
async def entered(message,state):
    await save(message,state,message.text or '')


@router.callback_query(Meeting.remove,F.data=='meet_remove_confirm')
async def removed(callback,state):
    await callback.answer()
    await save(callback,state,None)


@router.callback_query(F.data=='meet_remove_confirm')
async def stale(callback):
    await callback.answer('Відкрийте налаштування посилання знову.',show_alert=True)
