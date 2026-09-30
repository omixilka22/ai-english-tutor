"""Edit a weekly rule as a draft, committing only on explicit confirmation."""
from datetime import time
import re

from aiogram import F, Router
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.exc import SQLAlchemyError

from app.bot.ui import clear_flow, show_screen, keyboard, navigation, paginated_screen
from app.bot.keyboards.main import student_schedule_keyboard
from app.database.database import AsyncSessionLocal
from app.database.models import UserRole
from app.services.user_service import UserService
from app.services.teacher_service import TeacherService
from app.services.student_service import StudentService
from app.services.schedule_service import ScheduleService

router = Router(name='schedule_edit')
DAYS = ('Понеділок','Вівторок','Середа','Четвер','П’ятниця','Субота','Неділя')


class EditScheduleState(StatesGroup):
    review = State()
    day = State()
    time = State()
    duration = State()


async def access(session, telegram_id, student_id=None, schedule_id=None):

    user = await UserService.get_by_telegram_id(session, telegram_id)

    if user is None or user.role != UserRole.TEACHER:
        raise ValueError('Редагувати розклад може лише викладач.')

    teacher = await TeacherService.get_by_user_id(session, user.id)

    if teacher is None:
        raise ValueError('Профіль викладача не знайдено.')

    schedule = None

    if schedule_id is not None:
        schedule = await ScheduleService.get_by_id(session, schedule_id)

        if schedule is None or schedule.teacher_id != teacher.id or not schedule.active:
            raise ValueError('Розклад недоступний для редагування.')

        student_id = schedule.student_id

    student = await StudentService.get_by_id(session, student_id)

    if student is None or student.teacher_id != teacher.id:
        raise ValueError('Цей учень не належить вам.')

    return teacher, student, schedule


def values(schedule):
    return {'day_of_week':schedule.day_of_week, 'start_time':schedule.start_time.isoformat(),
            'duration_minutes':schedule.duration_minutes, 'timezone':schedule.timezone}


async def render_review(event, state, error=''):
    data = await state.get_data()

    text = (f"✎ Редагування розкладу · {data['student_name']}\n\n"
            f"{DAYS[data['day_of_week']]} · {data['start_time']}\n"
            f"Тривалість: {data['duration_minutes']} хв\nЧасовий пояс: {data['timezone']}\n\n"
            'Оберіть, що змінити. Потім збережіть зміни.\n'
            'Перенесені вручну та скасовані уроки залишаться без змін.')

    if error:
        text += '\n\n' + error
    await show_screen(event, state, text, reply_markup=keyboard([
        [('День','edit_field_day'),('Час','edit_field_time'),('Тривалість','edit_field_duration')],
        [('✓ Зберегти заняття без змін','edit_save')],
        [('✓ Оновити майбутні заняття','edit_save_future')],
        [('‹ Назад / скасувати',f"student_schedule_{data['student_id']}")],
        [('⌂ Головне меню','home')],
    ]))


@router.callback_query(F.data.regexp(r'^edit_student_schedule_\d+$'))
async def select_schedule(callback, state):
    await clear_flow(state)

    student_id = int(callback.data.rsplit('_',1)[1])
    async with AsyncSessionLocal() as session:
        try:
            teacher, student, _ = await access(session,callback.from_user.id,student_id=student_id)
        except ValueError as error:
            await callback.answer(str(error),show_alert=True)
            return
        schedules = await ScheduleService.get_by_student_id(session,student_id)
    rows = [[(f'{DAYS[s.day_of_week]} · {s.start_time:%H:%M} · {s.duration_minutes} хв',f'edit_schedule_{s.id}')]
            for s in sorted(schedules,key=lambda s:(s.day_of_week,s.start_time,s.id))
            if s.active and s.teacher_id == teacher.id]
    await callback.answer()
    await paginated_screen(callback,state,'✎ Оберіть запис розкладу' if rows else 'Немає активних записів для редагування.',
                           rows=rows,footer=navigation(f'student_schedule_{student_id}'))


@router.callback_query(F.data.regexp(r'^edit_schedule_\d+$'))
async def begin_edit(callback, state):
    schedule_id = int(callback.data.rsplit('_',1)[1])
    async with AsyncSessionLocal() as session:
        try:
            _,student,schedule = await access(session,callback.from_user.id,schedule_id=schedule_id)
        except ValueError as error:
            await callback.answer(str(error),show_alert=True)
            return
        user = await UserService.get_by_id(session,student.user_id)
        initial = values(schedule)
    await clear_flow(state)
    await state.update_data(schedule_id=schedule_id,student_id=student.id,
                            student_name=user.name if user else 'Учень',original=initial,**initial)
    await state.set_state(EditScheduleState.review)
    await callback.answer()
    await render_review(callback,state)


@router.callback_query(EditScheduleState.review,F.data.regexp(r'^edit_field_(day|time|duration)$'))
async def choose_field(callback,state):
    field = callback.data.rsplit('_',1)[1]
    data = await state.get_data()
    await state.set_state(getattr(EditScheduleState,field))
    rows = []
    if field == 'day':
        text = f"День тижня\n\nЗараз: {DAYS[data['day_of_week']]}"
        rows = [[(day,f'edit_day_{i}')] for i,day in enumerate(DAYS)]
    elif field == 'time':
        text = f"Час заняття\n\nЗараз: {data['start_time']} · {data['timezone']}\nВведіть новий час: HH:MM."
    else:
        text = f"Тривалість\n\nЗараз: {data['duration_minutes']} хв\nОберіть або введіть кількість хвилин (1–1440)."
        rows = [[(f'{n} хв',f'edit_duration_{n}') for n in (30,45,60)],
                [(f'{n} хв',f'edit_duration_{n}') for n in (90,120)]]
    rows += [[('‹ Назад','edit_review'),('⌂ Головне меню','home')]]
    await callback.answer()
    await show_screen(callback,state,text,reply_markup=keyboard(rows))


@router.callback_query(EditScheduleState.day,F.data.regexp(r'^edit_day_[0-6]$'))
async def change_day(callback,state):
    await state.update_data(day_of_week=int(callback.data.rsplit('_',1)[1]))
    await state.set_state(EditScheduleState.review)
    await callback.answer()
    await render_review(callback,state)


@router.callback_query(EditScheduleState.duration,F.data.regexp(r'^edit_duration_(30|45|60|90|120)$'))
async def change_duration(callback,state):
    await state.update_data(duration_minutes=int(callback.data.rsplit('_',1)[1]))
    await state.set_state(EditScheduleState.review)
    await callback.answer()
    await render_review(callback,state)


@router.message(EditScheduleState.time)
@router.message(EditScheduleState.duration)
async def enter_value(message,state):
    current = await state.get_state()
    raw = (message.text or '').strip()
    try:
        if current == EditScheduleState.time.state:
            if not re.fullmatch(r'[0-9]{2}:[0-9]{2}',raw):
                raise ValueError()
            hour,minute = map(int,raw.split(':'))
            value = time(hour,minute).isoformat()
            await state.update_data(start_time=value)
        else:
            if not re.fullmatch(r'[0-9]{1,4}',raw) or not 1 <= int(raw) <= 1440:
                raise ValueError()
            await state.update_data(duration_minutes=int(raw))
    except ValueError:
        hint = 'Введіть час від 00:00 до 23:59 у форматі HH:MM.' if current == EditScheduleState.time.state else 'Введіть цілу кількість хвилин від 1 до 1440.'
        await show_screen(message,state,hint,reply_markup=navigation('edit_review'))
        return
    await state.set_state(EditScheduleState.review)
    await render_review(message,state)


@router.callback_query(EditScheduleState.day,F.data == 'edit_review')
@router.callback_query(EditScheduleState.time,F.data == 'edit_review')
@router.callback_query(EditScheduleState.duration,F.data == 'edit_review')
async def back_to_review(callback,state):
    await state.set_state(EditScheduleState.review)
    await callback.answer()
    await render_review(callback,state)


@router.callback_query(EditScheduleState.review,F.data.in_({'edit_save','edit_save_future'}))
async def save_edit(callback,state):
    data = await state.get_data()
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            _,student,schedule = await access(session,callback.from_user.id,schedule_id=data['schedule_id'])
            if student.id != data['student_id'] or values(schedule) != data['original']:
                raise ValueError('Розклад уже змінився. Відкрийте його знову для редагування.')
            await ScheduleService.update_schedule(session,schedule,
                day_of_week=data['day_of_week'],start_time=time.fromisoformat(data['start_time']),
                duration_minutes=data['duration_minutes'],timezone=data['timezone'],
                apply_future=callback.data=='edit_save_future',expected=data['original'])
        except ValueError as error:
            await session.rollback()
            await clear_flow(state)
            await show_screen(callback,state,str(error),reply_markup=navigation(f"student_schedule_{data['student_id']}"))
            return
        except SQLAlchemyError:
            await session.rollback()
            await render_review(callback,state,'Не вдалося зберегти. Спробуйте ще раз.')
            return
    await clear_flow(state)
    await show_screen(callback,state,'✓ Розклад оновлено.',reply_markup=student_schedule_keyboard(data['student_id']))


@router.callback_query(F.data.startswith('edit_field_') | F.data.startswith('edit_day_') |
                       F.data.startswith('edit_duration_') | F.data.in_({'edit_review','edit_save','edit_save_future'}))
async def stale_edit(callback):
    await callback.answer('Редагування вже закрито. Відкрийте розклад знову.',show_alert=True)
