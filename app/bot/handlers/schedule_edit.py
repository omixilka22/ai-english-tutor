"""Compatibility for buttons from the former permanent-template UI."""
from aiogram import F, Router
from app.bot.ui import clear_flow, show_screen, navigation
router = Router(name='schedule_edit')


@router.callback_query(F.data.startswith('edit_student_schedule_') | F.data.startswith('edit_schedule_') |
                       F.data.startswith('edit_field_') | F.data.startswith('edit_day_') |
                       F.data.startswith('edit_duration_') | F.data.in_({'edit_review','edit_save','edit_save_future'}))
async def stale_edit(callback, state):
    await callback.answer()
    await clear_flow(state)
    await show_screen(callback, state,
        'Розклад тепер складається з конкретних занять на тиждень. Відкрийте заняття, щоб перенести або скасувати його.',
        reply_markup=navigation('student_schedule'))
