from aiogram import Router, F
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.exc import SQLAlchemyError
from app.bot.ui import clear_flow, show_screen, keyboard, navigation
from app.database.database import AsyncSessionLocal
from app.services.calendar_service import CalendarService
from app.services.student_removal import remove_student

router=Router(name='student_removal')

class Removal(StatesGroup):
    confirm=State()

@router.callback_query(F.data.regexp(r'^remove_student_\d+$'))
async def begin(callback,state):
    await callback.answer()
    student_id=int(callback.data.rsplit('_',1)[1])
    async with AsyncSessionLocal() as session:
        try:
            await CalendarService.student_access(session,callback.from_user.id,student_id,write=True)
        except ValueError as error:
            await show_screen(callback,state,str(error),reply_markup=navigation('my_students'))
            return
    await clear_flow(state)
    await state.set_state(Removal.confirm)
    await state.update_data(remove_student_id=student_id)
    await show_screen(callback,state,
        'Видалити учня зі свого списку?\n\n'
        'Поточне непідтверджене та майбутні заняття буде прибрано, розклад і нагадування вимкнено. '
        'Посилання Meet буде відв’язано.\n\n'
        'Історія проведених уроків і надіслані матеріали залишаться в учня. '
        'Щоб знову додати учня, знадобиться нове запрошення.',
        reply_markup=keyboard([[('Так, видалити зі списку',f'remove_student_confirm_{student_id}')],
            [('‹ Скасувати',f'student_{student_id}'),('⌂ Головне меню','home')]]))

@router.callback_query(Removal.confirm,F.data.regexp(r'^remove_student_confirm_\d+$'))
async def confirm(callback,state):
    await callback.answer()
    student_id=int(callback.data.rsplit('_',1)[1])
    data=await state.get_data()
    if data.get('remove_student_id')!=student_id:
        await show_screen(callback,state,'Відкрийте картку учня та підтвердьте видалення знову.',reply_markup=navigation('my_students'))
        return
    async with AsyncSessionLocal() as session:
        try:
            await remove_student(session,callback.from_user.id,student_id)
        except (ValueError,SQLAlchemyError) as error:
            await session.rollback()
            await show_screen(callback,state,str(error) if isinstance(error,ValueError) else 'Не вдалося видалити учня. Спробуйте ще раз.',reply_markup=navigation('my_students'))
            return
    await clear_flow(state)
    await show_screen(callback,state,'✓ Учня видалено зі списку.',reply_markup=navigation('my_students'))

@router.callback_query(F.data.regexp(r'^remove_student_confirm_\d+$'))
async def stale(callback):
    await callback.answer('Відкрийте картку учня та підтвердьте видалення знову.',show_alert=True)
