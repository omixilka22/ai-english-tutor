"""Upcoming lessons, detail, and teacher-only rescheduling/cancellation."""
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import F, Router
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.exc import SQLAlchemyError
from app.bot.ui import clear_flow, show_screen, paginated_screen, keyboard, navigation
from app.database.database import AsyncSessionLocal
from app.database.models import LessonStatus
from app.services.calendar_service import CalendarService, utcnow
from app.services.recurrence import local_instant

from app.bot.handlers.extra_lesson import router as extra_router

router = Router(name='lessons')
router.include_router(extra_router)
LABELS = {LessonStatus.SCHEDULED:'Заплановано',LessonStatus.CANCELLED:'Скасовано',
          LessonStatus.COMPLETED:'Завершено',LessonStatus.PROCESSING:'Обробка',
          LessonStatus.READY_FOR_REVIEW:'На перевірці',LessonStatus.APPROVED:'Підтверджено',LessonStatus.SENT:'Надіслано'}


class LessonEdit(StatesGroup):
    date = State()
    confirm = State()
    cancel = State()
    restore = State()
    delete = State()


def local_label(lesson):
    return lesson.scheduled_at.astimezone(ZoneInfo(lesson.timezone)).strftime('%d.%m.%Y · %H:%M')


@router.callback_query(F.data.in_({'my_lessons','notification_list'}))
@router.callback_query(F.data.regexp(r'^student_lessons_\d+$'))
async def lesson_list(callback,state):
    await clear_flow(state)
    student_id = int(callback.data.rsplit('_',1)[1]) if callback.data.startswith('student_lessons_') else None
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            student,teacher,lessons = await CalendarService.upcoming(session,callback.from_user.id,student_id)
        except (ValueError,SQLAlchemyError) as error:
            await session.rollback()
            await show_screen(callback,state,str(error) if isinstance(error,ValueError) else 'Не вдалося завантажити заняття. Спробуйте знову.')
            return
    rows = [[(f'{local_label(l)} · {LABELS[l.status]}',f'lesson_{l.id}')] for l in lessons]
    footer = navigation(f'student_{student.id}' if teacher else 'home')
    if teacher:
        footer.inline_keyboard.insert(0,keyboard([[('＋ Додаткове заняття',f'extra_lesson_{student.id}')]]).inline_keyboard[0])
    await paginated_screen(callback,state,'📚 Найближчі заняття\nГоризонт генерації — 4 тижні.' if rows else '📚 Занять поки немає. Можна додати розклад або разове заняття.',
        rows=rows,footer=footer)


@router.callback_query(F.data.regexp(r'^(lesson|notification_lesson)_\d+$'))
async def detail(callback,state):
    await clear_flow(state)
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            lesson,teacher = await CalendarService.lesson_access(session,callback.from_user.id,int(callback.data.rsplit('_',1)[1]))
        except ValueError as error:
            await show_screen(callback,state,str(error))
            return
    rows=[]
    if teacher and lesson.status==LessonStatus.SCHEDULED and lesson.scheduled_at>utcnow():
        rows += [[('✎ Перенести',f'move_lesson_{lesson.id}'),('Скасувати заняття',f'cancel_lesson_{lesson.id}')]]
    if teacher and lesson.status==LessonStatus.CANCELLED and lesson.scheduled_at>utcnow():
        rows += [[('↶ Відновити заняття',f'restore_lesson_{lesson.id}')]]
    if teacher:
        rows += [[('🗑 Видалити заняття',f'delete_lesson_{lesson.id}')]]
    rows += [[('‹ До занять',f'student_lessons_{lesson.student_id}' if teacher else 'my_lessons'),('⌂ Головне меню','home')]]
    title = '📚 Додаткове заняття · без повторення' if getattr(lesson,'schedule_id',1) is None else '📚 Заняття'
    await show_screen(callback,state,f'{title}\n\n{local_label(lesson)}\n{lesson.timezone}\n'
        f'{lesson.duration_minutes} хв · {LABELS[lesson.status]}',reply_markup=keyboard(rows))


@router.callback_query(F.data.regexp(r'^(move|cancel)_lesson_\d+$'))
async def begin_change(callback,state):
    await clear_flow(state)
    lesson_id = int(callback.data.rsplit('_',1)[1])
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            lesson,_ = await CalendarService.lesson_access(session,callback.from_user.id,lesson_id,write=True)
            if lesson.status!=LessonStatus.SCHEDULED or lesson.scheduled_at<=utcnow():
                raise ValueError('Це заняття вже не можна змінити.')
        except ValueError as error:
            await show_screen(callback,state,str(error))
            return
    await state.update_data(lesson_id=lesson_id,timezone=lesson.timezone)
    if callback.data.startswith('cancel_'):
        await state.set_state(LessonEdit.cancel)
        await show_screen(callback,state,f'Скасувати заняття {local_label(lesson)}?\n\nЩотижневий розклад залишиться без змін.',
            reply_markup=keyboard([[('Так, скасувати','lesson_cancel_confirm')],[('‹ Назад',f'lesson_{lesson_id}'),('⌂ Головне меню','home')]]))
    else:
        await state.set_state(LessonEdit.date)
        await show_screen(callback,state,f'Нова дата заняття\n\nЗараз: {local_label(lesson)}\nЧасовий пояс: {lesson.timezone}\n'
            'Введіть ДД.ММ.РРРР ГГ:ХХ, наприклад 15.10.2026 18:30.',reply_markup=navigation(f'lesson_{lesson_id}'))


@router.callback_query(F.data.regexp(r'^(restore|delete)_lesson_\d+$'))
async def begin_restore_delete(callback,state):
    await clear_flow(state)
    await callback.answer()
    action = callback.data.split('_')[0]
    lesson_id = int(callback.data.rsplit('_',1)[1])
    async with AsyncSessionLocal() as session:
        try:
            lesson,_ = await CalendarService.lesson_access(session,callback.from_user.id,lesson_id,write=True)
            if action=='restore' and (lesson.status!=LessonStatus.CANCELLED or lesson.scheduled_at<=utcnow()):
                raise ValueError('Відновити можна лише скасоване майбутнє заняття.')
        except ValueError as error:
            await show_screen(callback,state,str(error))
            return
    await state.update_data(lesson_id=lesson_id,student_id=lesson.student_id)
    await state.set_state(LessonEdit.restore if action=='restore' else LessonEdit.delete)
    text = (f'Відновити заняття {local_label(lesson)}?\n\nДата і тривалість залишаться незмінними.'
            if action=='restore' else f'Видалити заняття {local_label(lesson)}?\n\n'
            'Воно зникне зі списків викладача й учня та не буде створене повторно. '
            'Повернення через меню буде недоступне. Щотижневий розклад не зміниться.')
    await show_screen(callback,state,text,reply_markup=keyboard([
        [('Так, відновити' if action=='restore' else 'Так, видалити',f'lesson_{action}_confirm')],
        [('‹ Назад',f'lesson_{lesson_id}'),('⌂ Головне меню','home')]]))


@router.callback_query(LessonEdit.restore,F.data=='lesson_restore_confirm')
@router.callback_query(LessonEdit.delete,F.data=='lesson_delete_confirm')
async def confirm_restore_delete(callback,state):
    data = await state.get_data()
    await callback.answer()
    deleting = callback.data=='lesson_delete_confirm'
    async with AsyncSessionLocal() as session:
        try:
            operation = CalendarService.delete_lesson if deleting else CalendarService.restore_lesson
            await operation(session,callback.from_user.id,data['lesson_id'])
        except (ValueError,SQLAlchemyError) as error:
            await session.rollback()
            await clear_flow(state)
            await show_screen(callback,state,str(error) if isinstance(error,ValueError) else 'Зміни не збережено. Спробуйте ще раз.',
                reply_markup=navigation(f"student_lessons_{data['student_id']}"))
            return
    await clear_flow(state)
    await show_screen(callback,state,'✓ Заняття видалено.' if deleting else '✓ Заняття відновлено.',
        reply_markup=navigation(f"student_lessons_{data['student_id']}" if deleting else f"lesson_{data['lesson_id']}"))


@router.message(LessonEdit.date)
async def enter_date(message,state):
    data = await state.get_data()
    try:
        naive = datetime.strptime(message.text or '', '%d.%m.%Y %H:%M')
        instant = local_instant(naive.date(),naive.time(),data['timezone'],strict=True)
        if instant<=utcnow():
            raise ValueError('Дата повинна бути в майбутньому.')
    except ValueError:
        await show_screen(message,state,'Вкажіть майбутню дату у форматі ДД.ММ.РРРР ГГ:ХХ.\n'
            'Час має однозначно існувати у вашому часовому поясі.',reply_markup=navigation(f"lesson_{data['lesson_id']}"))
        return
    await state.update_data(scheduled_at=instant.isoformat())
    await state.set_state(LessonEdit.confirm)
    await show_screen(message,state,f"Перенести заняття на {naive:%d.%m.%Y %H:%M}?\n{data['timezone']}\nЩотижневий розклад не зміниться.",
        reply_markup=keyboard([[('✓ Підтвердити','lesson_move_confirm')],[('‹ Ввести іншу дату',f"move_lesson_{data['lesson_id']}")],[('Скасувати',f"lesson_{data['lesson_id']}"),('⌂ Головне меню','home')]]))


@router.callback_query(LessonEdit.confirm,F.data=='lesson_move_confirm')
@router.callback_query(LessonEdit.cancel,F.data=='lesson_cancel_confirm')
async def confirm_change(callback,state):
    data = await state.get_data()
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            await CalendarService.change_lesson(session,callback.from_user.id,data['lesson_id'],
                cancel=callback.data=='lesson_cancel_confirm',
                scheduled_at=datetime.fromisoformat(data['scheduled_at']) if 'scheduled_at' in data else None)
        except (ValueError,SQLAlchemyError) as error:
            await session.rollback()
            await clear_flow(state)
            await show_screen(callback,state,str(error) if isinstance(error,ValueError) else 'Зміни не збережено. Відкрийте заняття і спробуйте знову.',
                              reply_markup=navigation(f"lesson_{data['lesson_id']}"))
            return
    await clear_flow(state)
    await show_screen(callback,state,'✓ Заняття скасовано.' if callback.data=='lesson_cancel_confirm' else '✓ Заняття перенесено.',
                      reply_markup=navigation(f"lesson_{data['lesson_id']}"))


@router.callback_query(F.data.in_({'lesson_move_confirm','lesson_cancel_confirm','lesson_restore_confirm','lesson_delete_confirm'}))
async def stale(callback):
    await callback.answer('Цю дію вже завершено. Відкрийте заняття знову.',show_alert=True)
