"""Schedule views and an editable four-step creation wizard."""
import re
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo
from app.services.recurrence import week_monday
from app.services.week_service import week_lessons, decide, validate_target
from app.services.calendar_service import utcnow
from app.workers.week_renewal import renewal_keyboard

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from sqlalchemy.exc import SQLAlchemyError

from app.bot.keyboards.main import schedule_menu_keyboard, student_schedule_keyboard
from app.bot.states.schedule import ScheduleState
from app.bot.ui import keyboard, navigation, clear_flow, show_screen, paginated_screen
from app.database.database import AsyncSessionLocal
from app.database.models import UserRole
from app.services.user_service import UserService
from app.services.teacher_service import TeacherService
from app.services.student_service import StudentService
from app.services.schedule_service import ScheduleService

from app.bot.handlers.schedule_edit import router as edit_router

router = Router(name="schedules")
router.include_router(edit_router)
DAYS = ("Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя")
TIMEZONE = "Europe/Kyiv"


def parse_time(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value.strip()):
        raise ValueError("Введіть час у форматі HH:MM, наприклад 18:30.")
    try:
        hour, minute = map(int, value.strip().split(":"))
        return time(hour, minute)
    except ValueError:
        raise ValueError("Час має бути від 00:00 до 23:59.") from None


def format_schedule(schedule):
    return (f"{DAYS[schedule.day_of_week]}, {schedule.start_time:%H:%M}, "
            f"{schedule.duration_minutes} хв · {schedule.timezone}")


async def teacher_for(session, telegram_id):
    user = await UserService.get_by_telegram_id(session, telegram_id)
    if user is None or user.role != UserRole.TEACHER:
        raise ValueError("Ця дія доступна тільки викладачу. Скористайтеся /start.")
    teacher = await TeacherService.get_by_user_id(session, user.id)
    if teacher is None:
        raise ValueError("Профіль викладача не знайдено.")
    return teacher


async def owned_student(session, teacher_id, student_id):
    student = await StudentService.get_by_id(session, student_id)
    if student is None or student.teacher_id != teacher_id:
        raise ValueError("Учня не знайдено або він не належить вам.")
    return student


@router.callback_query(F.data == 'schedule_menu')
async def schedule_menu(callback, state: FSMContext):
    await clear_flow(state)
    async with AsyncSessionLocal() as session:
        try:
            await teacher_for(session, callback.from_user.id)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
    await callback.answer()
    await show_screen(callback, state, '📅 Розклад\n\nПерегляньте тиждень або оберіть учня.',
                      reply_markup=schedule_menu_keyboard())


def selected_week(callback):
    tail = callback.data.rsplit('_', 1)[-1]
    return date.fromisoformat(tail) if '-' in tail else week_monday()


def week_title(week):
    return f'{week:%d.%m}–{week + timedelta(days=6):%d.%m.%Y}'


@router.callback_query(F.data == 'general_schedule')
@router.callback_query(F.data.startswith('week_view_'))
async def general_schedule(callback, state: FSMContext):
    week = selected_week(callback)
    await clear_flow(state)
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            validate_target(week, utcnow())
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        students = await StudentService.get_by_teacher_id(session, teacher.id)
        names = {student.id: user.name for student, user in students}
        lessons = await week_lessons(session, teacher.id, week)
    from app.bot.handlers.lessons import attendance_label
    rows = [[(f'{l.scheduled_at.astimezone(ZoneInfo(TIMEZONE)):%d.%m %H:%M} · {names.get(l.student_id, "Учень")} · {attendance_label(l)}', f'lesson_{l.id}')] for l in lessons]
    other = week_monday() + timedelta(days=7) if week == week_monday() else week_monday()
    footer = keyboard([
        [('＋ Додати заняття', f'week_students_{week.isoformat()}')],
        [('Повторити попередній / скласти новий', f'week_plan_{week.isoformat()}')],
        [(f'Тиждень {week_title(other)}', f'week_view_{other.isoformat()}')],
        [('‹ Назад', 'schedule_menu'), ('⌂ Головне меню', 'home')]])
    await callback.answer()
    await paginated_screen(callback, state, f'📅 {week_title(week)}' + ('\nЗанять поки немає.' if not rows else ''), rows=rows, footer=footer)


@router.callback_query(F.data == 'student_schedule')
@router.callback_query(F.data.startswith('week_students_'))
async def select_student(callback, state: FSMContext):
    week = selected_week(callback)
    await clear_flow(state)
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            validate_target(week, utcnow())
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        students = await StudentService.get_by_teacher_id(session, teacher.id)
    await callback.answer()
    await paginated_screen(callback, state, f'👤 Оберіть учня · {week_title(week)}',
        rows=[[(u.name, f'week_student_{s.id}_{week.isoformat()}')] for s,u in students],
        footer=navigation(f'week_view_{week.isoformat()}'))


@router.callback_query(F.data.regexp(r'^student_schedule_\d+$'))
@router.callback_query(F.data.regexp(r'^week_student_\d+_\d{4}-\d{2}-\d{2}$'))
async def student_schedule(callback, state: FSMContext):
    week = selected_week(callback)
    student_id = int(callback.data.split('_')[2])
    await clear_flow(state)
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            student = await owned_student(session, teacher.id, student_id)
            validate_target(week, utcnow())
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        user = await UserService.get_by_id(session, student.user_id)
        lessons = await week_lessons(session, teacher.id, week, student_id)
    from app.bot.handlers.lessons import attendance_label
    rows = [[(f'{l.scheduled_at.astimezone(ZoneInfo(TIMEZONE)):%d.%m %H:%M} · {attendance_label(l)}', f'lesson_{l.id}')] for l in lessons]
    other = week_monday() + timedelta(days=7) if week == week_monday() else week_monday()
    await callback.answer()
    await paginated_screen(callback, state, f'📅 {user.name if user else student_id} · {week_title(week)}',
        rows=rows, footer=keyboard([
            [('＋ Заняття цього тижня', f'week_add_{student_id}_{week.isoformat()}')],
            [('＋ Разове додаткове', f'extra_lesson_{student_id}')],
            [(f'Тиждень {week_title(other)}', f'week_student_{student_id}_{other.isoformat()}')],
            [('‹ Назад', f'week_view_{week.isoformat()}'), ('⌂ Головне меню', 'home')]]))


@router.callback_query(F.data.startswith('week_plan_'))
async def plan_week(callback, state):
    week = selected_week(callback)
    async with AsyncSessionLocal() as session:
        try:
            await teacher_for(session, callback.from_user.id)
            validate_target(week, utcnow())
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
    await callback.answer()
    await clear_flow(state)
    await show_screen(callback, state, f'📅 {week_title(week)}\n\nПовторити фактичні дні й час попереднього тижня? Разові додаткові та скасовані заняття не копіюються. Уже створені заняття зберігаються.', reply_markup=renewal_keyboard(week))


@router.callback_query(F.data.startswith('week_repeat_') | F.data.startswith('week_new_'))
async def decide_week(callback, state):
    week = selected_week(callback)
    repeat = callback.data.startswith('week_repeat_')
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            count, decision = await decide(session, teacher.id, week, repeat=repeat)
        except (ValueError, SQLAlchemyError) as error:
            await session.rollback()
            text = str(error) if isinstance(error, ValueError) else 'Не вдалося зберегти. Спробуйте ще раз.'
            await show_screen(callback, state, text, reply_markup=navigation('schedule_menu'))
            return
    await clear_flow(state)
    text = (f'✓ Створено занять: {count}. Учні вже бачать їх у розкладі.' if count else
            'Рішення збережено. Ви можете додати заняття або змінити вже створені.')
    await show_screen(callback, state, f'📅 {week_title(week)}\n\n{text}', reply_markup=keyboard([
        [('＋ Скласти / доповнити розклад', f'week_students_{week.isoformat()}')],
        [('Переглянути заняття', f'week_view_{week.isoformat()}')],
        [('⌂ Головне меню', 'home')]]))


async def render_wizard(event, state, error=''):
    data = await state.get_data()
    current = await state.get_state()
    name = data.get('student_name') or f"Учень #{data['student_id']}"
    week = date.fromisoformat(data.get('week_start', week_monday().isoformat()))
    title = f'📅 {name} · {week_title(week)}\n'
    summary = ''
    if current == ScheduleState.choosing_day.state:
        text = 'Крок 1 / 4 · День тижня\n\nКоли відбуватиметься заняття?'
        rows = [[(DAYS[i],f'schedule_day_{i}') for i in range(start,min(start+2,7))]
                for start in range(0,7,2)]
        back = f"week_student_{data['student_id']}_{week.isoformat()}"
    else:
        summary = f"{DAYS[data['day_of_week']]} · {TIMEZONE}\n\n"
        back = 'schedule_back'
        if current == ScheduleState.waiting_for_time.state:
            text = 'Крок 2 / 4 · Час\n\n' + summary + 'Напишіть час у форматі HH:MM, наприклад 18:30.'
            rows = []
        elif current == ScheduleState.choosing_duration.state:
            text = 'Крок 3 / 4 · Тривалість\n\n' + summary + f"Початок: {data['start_time']}\nОберіть тривалість заняття."
            rows = [[(f'{n} хв',f'schedule_duration_{n}') for n in values]
                    for values in [(30,45,60),(90,120)]]
        else:
            text = ('Крок 4 / 4 · Підтвердження\n\n' + summary
                    + f"Початок: {data['start_time']}\nТривалість: {data['duration_minutes']} хв\nЛише на вибраний тиждень. Після збереження заняття бачить учень.")
            rows = [[('✓ Зберегти розклад','schedule_confirm')]]
    if error:
        text += '\n\n' + error
    rows += [[('‹ Назад',back),('Скасувати','schedule_cancel')], [('⌂ Головне меню','home')]]
    await show_screen(event, state, title + text, reply_markup=keyboard(rows))


@router.callback_query(F.data.regexp(r'^add_schedule_\d+$'))
@router.callback_query(F.data.regexp(r'^week_add_\d+_\d{4}-\d{2}-\d{2}$'))
async def add_schedule(callback, state: FSMContext):
    student_id = int(callback.data.split('_')[2])
    week = selected_week(callback)
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            student = await owned_student(session, teacher.id, student_id)
            validate_target(week, utcnow())
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        user = await UserService.get_by_id(session, student.user_id)
    await clear_flow(state)
    await state.update_data(student_id=student_id, student_name=user.name if user else None, week_start=week.isoformat())
    await state.set_state(ScheduleState.choosing_day)
    await callback.answer()
    await render_wizard(callback, state)


@router.callback_query(ScheduleState.choosing_day, F.data.regexp(r'^schedule_day_[0-6]$'))
async def choose_day(callback, state: FSMContext):
    await state.update_data(day_of_week=int(callback.data.rsplit('_',1)[1]))
    await state.set_state(ScheduleState.waiting_for_time)
    await callback.answer()
    await render_wizard(callback, state)


@router.message(ScheduleState.waiting_for_time)
async def enter_time(message, state: FSMContext):
    try:
        value = parse_time(message.text)
    except ValueError as error:
        await render_wizard(message, state, str(error))
        return
    await state.update_data(start_time=value.strftime('%H:%M'))
    await state.set_state(ScheduleState.choosing_duration)
    await render_wizard(message, state)


@router.callback_query(ScheduleState.choosing_duration, F.data.regexp(r'^schedule_duration_(30|45|60|90|120)$'))
async def choose_duration(callback, state: FSMContext):
    await state.update_data(duration_minutes=int(callback.data.rsplit('_',1)[1]))
    await state.set_state(ScheduleState.confirming)
    await callback.answer()
    await render_wizard(callback, state)


@router.callback_query(ScheduleState.waiting_for_time, F.data == 'schedule_back')
@router.callback_query(ScheduleState.choosing_duration, F.data == 'schedule_back')
@router.callback_query(ScheduleState.confirming, F.data == 'schedule_back')
async def schedule_back(callback, state: FSMContext):
    current = await state.get_state()
    previous = {ScheduleState.waiting_for_time.state:ScheduleState.choosing_day,
                ScheduleState.choosing_duration.state:ScheduleState.waiting_for_time,
                ScheduleState.confirming.state:ScheduleState.choosing_duration}
    await state.set_state(previous[current])
    await callback.answer()
    await render_wizard(callback, state)


@router.callback_query(F.data == 'schedule_cancel')
async def cancel_schedule(callback, state: FSMContext):
    data = await state.get_data()
    student_id = data.get('student_id')
    week = data.get('week_start', week_monday().isoformat())
    await clear_flow(state)
    await callback.answer()
    await show_screen(callback, state, 'Створення розкладу скасовано.',
        reply_markup=navigation(f'week_student_{student_id}_{week}' if student_id else 'schedule_menu'))


@router.callback_query(ScheduleState.confirming, F.data == 'schedule_confirm')
async def confirm_schedule(callback, state: FSMContext):
    data = await state.get_data()
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            await owned_student(session, teacher.id, data['student_id'])
            await ScheduleService.create_schedule(session,teacher_id=teacher.id,student_id=data['student_id'],
                day_of_week=data['day_of_week'],start_time=parse_time(data['start_time']),
                duration_minutes=data['duration_minutes'],timezone=TIMEZONE, week_start=date.fromisoformat(data.get('week_start', week_monday().isoformat())))
        except ValueError as error:
            await session.rollback()
            await render_wizard(callback, state, str(error))
            return
        except SQLAlchemyError:
            await session.rollback()
            await render_wizard(callback, state, 'Не вдалося зберегти. Спробуйте підтвердити ще раз.')
            return
    await clear_flow(state)
    await show_screen(callback, state,
        f"✓ Розклад збережено\n\n{data.get('student_name') or 'Учень'}\n"
        f"{DAYS[data['day_of_week']]} · {data['start_time']} · {data['duration_minutes']} хв\n{TIMEZONE}",
        reply_markup=navigation(f"week_student_{data['student_id']}_{data['week_start']}"))


@router.callback_query(F.data.startswith('schedule_day_') | F.data.startswith('schedule_duration_') |
                       (F.data == 'schedule_confirm') | (F.data == 'schedule_back'))
async def stale_schedule_button(callback):
    await callback.answer('Ця кнопка вже неактивна. Відкрийте розклад учня знову.',show_alert=True)
