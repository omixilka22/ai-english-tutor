from aiogram import F,Router
from sqlalchemy import select
from app.database.database import AsyncSessionLocal
from app.database.models import Student,User,UserRole
from app.services.notification_service import set_preference
from app.bot.ui import clear_flow,show_screen,keyboard

router=Router(name='notification_settings')


@router.callback_query(F.data.in_({'notification_settings','reminders_on','reminders_off'}))
async def settings(callback,state):
    await clear_flow(state)
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            if callback.data in ('reminders_on','reminders_off'):
                student=await set_preference(session,callback.from_user.id,callback.data=='reminders_on')
            else:
                user=(await session.execute(select(User).where(User.telegram_id==callback.from_user.id))).scalar_one_or_none()
                if user is None or user.role!=UserRole.STUDENT:
                    raise ValueError('Це налаштування доступне лише учню.')
                student=(await session.execute(select(Student).where(Student.user_id==user.id))).scalar_one_or_none()
                if student is None:
                    raise ValueError('Профіль учня не знайдено.')
        except ValueError as error:
            await show_screen(callback,state,str(error))
            return
    text=('🔔 Нагадування\n\nСтан: '+('увімкнено' if student.reminders_enabled else 'вимкнено')+
          '\nЗа 12 годин та за 1 годину до заняття.\n\n'
          'Повідомлення про перенесення, скасування й відновлення надходять незалежно від цього налаштування.')
    await show_screen(callback,state,text,reply_markup=keyboard([
        [('Вимкнути' if student.reminders_enabled else 'Увімкнути','reminders_off' if student.reminders_enabled else 'reminders_on')],
        [('‹ Назад','home')]]))
