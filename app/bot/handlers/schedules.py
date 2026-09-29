"""Teacher schedule browsing and the weekly schedule creation conversation."""
import re
from datetime import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.exc import SQLAlchemyError

from app.bot.keyboards.main import (
    schedule_menu_keyboard, student_schedule_keyboard, teacher_main_menu_keyboard,
)
from app.bot.states.schedule import ScheduleState
from app.database.database import AsyncSessionLocal
from app.database.models import UserRole
from app.services.user_service import UserService
from app.services.teacher_service import TeacherService
from app.services.student_service import StudentService
from app.services.schedule_service import ScheduleService

router = Router(name="schedules")
DAYS = ("Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя")
TIMEZONE = "Europe/Kyiv"


def keyboard(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
        for row in rows
    ])


def cancel_row():
    return [("Скасувати", "schedule_cancel")]


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


async def send_lines(message, title, lines, reply_markup):
    # Keep each Telegram message below the text limit, even for a large roster.
    chunk = title
    for line in lines or ["Розклад поки порожній."]:
        line = line[:1000]
        if len(chunk) + len(line) + 1 > 3500:
            await message.answer(chunk)
            chunk = title
        chunk += "\n" + line
    await message.answer(chunk, reply_markup=reply_markup)


@router.callback_query(F.data == "schedule_menu")
async def schedule_menu(callback, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
        try:
            await teacher_for(session, callback.from_user.id)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
    await callback.answer()
    await callback.message.answer("📅 Розклад", reply_markup=schedule_menu_keyboard())


@router.callback_query(F.data == "general_schedule")
async def general_schedule(callback, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        students = await StudentService.get_by_teacher_id(session, teacher.id)
        names = {student.id: user.name for student, user in students}
        schedules = await ScheduleService.get_by_teacher_id(session, teacher.id)
    lines = [f"• {names.get(s.student_id, 'Учень #' + str(s.student_id))}: {format_schedule(s)}"
             for s in sorted(schedules, key=lambda s: (s.day_of_week, s.start_time, s.id))
             if s.active and s.student_id in names]
    await callback.answer()
    await send_lines(callback.message, "📅 Загальний розклад", lines, schedule_menu_keyboard())


@router.callback_query(F.data == "student_schedule")
async def select_student(callback, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        students = await StudentService.get_by_teacher_id(session, teacher.id)
    await callback.answer()
    if not students:
        await callback.message.answer("У вас поки немає учнів. Спочатку запросіть учня.",
                                      reply_markup=teacher_main_menu_keyboard())
        return
    # Bound the number of buttons per message.
    for offset in range(0, len(students), 40):
        await callback.message.answer("Оберіть учня:", reply_markup=keyboard([
            [(user.name, f"student_schedule_{student.id}")]
            for student, user in students[offset:offset + 40]
        ]))


@router.callback_query(F.data.regexp(r"^student_schedule_\d+$"))
async def student_schedule(callback, state: FSMContext):
    await state.clear()
    student_id = int(callback.data.rsplit("_", 1)[1])
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            student = await owned_student(session, teacher.id, student_id)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        user = await UserService.get_by_id(session, student.user_id)
        schedules = await ScheduleService.get_by_student_id(session, student_id)
    lines = [f"• {format_schedule(s)}"
             for s in sorted(schedules, key=lambda s: (s.day_of_week, s.start_time, s.id))
             if s.active and s.teacher_id == teacher.id]
    await callback.answer()
    await send_lines(callback.message, f"📅 Розклад: {user.name if user else student_id}",
                     lines, student_schedule_keyboard(student_id))


@router.callback_query(F.data.regexp(r"^add_schedule_\d+$"))
async def add_schedule(callback, state: FSMContext):
    student_id = int(callback.data.rsplit("_", 1)[1])
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            await owned_student(session, teacher.id, student_id)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
    await state.clear()
    await state.update_data(student_id=student_id)
    await state.set_state(ScheduleState.choosing_day)
    await callback.answer()
    await callback.message.answer("Оберіть день тижня:", reply_markup=keyboard(
        [[(name, f"schedule_day_{i}")] for i, name in enumerate(DAYS)] + [cancel_row()]))


@router.callback_query(ScheduleState.choosing_day, F.data.regexp(r"^schedule_day_[0-6]$"))
async def choose_day(callback, state: FSMContext):
    await state.update_data(day_of_week=int(callback.data.rsplit("_", 1)[1]))
    await state.set_state(ScheduleState.waiting_for_time)
    await callback.answer()
    await callback.message.answer(f"Введіть час у форматі HH:MM (наприклад 18:30).\nЧасовий пояс: {TIMEZONE}.",
                                  reply_markup=keyboard([cancel_row()]))


@router.message(Command("cancel"))
async def cancel_command(message, state: FSMContext):
    await state.clear()
    await message.answer("Поточну дію скасовано. /start — головне меню.")


@router.callback_query(F.data == "schedule_cancel")
async def cancel_schedule(callback, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.answer("Створення розкладу скасовано. /start — головне меню.")


@router.message(ScheduleState.waiting_for_time)
async def enter_time(message, state: FSMContext):
    try:
        value = parse_time(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    await state.update_data(start_time=value.strftime("%H:%M"))
    await state.set_state(ScheduleState.choosing_duration)
    await message.answer("Оберіть тривалість:", reply_markup=keyboard([
        [(f"{n} хв", f"schedule_duration_{n}") for n in (30, 45, 60)],
        [(f"{n} хв", f"schedule_duration_{n}") for n in (90, 120)],
        cancel_row(),
    ]))


@router.callback_query(ScheduleState.choosing_duration,
                       F.data.regexp(r"^schedule_duration_(30|45|60|90|120)$"))
async def choose_duration(callback, state: FSMContext):
    duration = int(callback.data.rsplit("_", 1)[1])
    await state.update_data(duration_minutes=duration)
    data = await state.get_data()
    await state.set_state(ScheduleState.confirming)
    await callback.answer()
    await callback.message.answer(
        f"Зберегти щотижневий розклад для учня #{data['student_id']}?\n"
        f"{DAYS[data['day_of_week']]}, {data['start_time']}, {duration} хв\n{TIMEZONE}",
        reply_markup=keyboard([[("✅ Зберегти", "schedule_confirm")], cancel_row()]))


@router.callback_query(ScheduleState.confirming, F.data == "schedule_confirm")
async def confirm_schedule(callback, state: FSMContext):
    data = await state.get_data()
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            await owned_student(session, teacher.id, data["student_id"])
            await ScheduleService.create_schedule(
                session, teacher_id=teacher.id, student_id=data["student_id"],
                day_of_week=data["day_of_week"], start_time=parse_time(data["start_time"]),
                duration_minutes=data["duration_minutes"], timezone=TIMEZONE,
            )
        except ValueError as error:
            await state.clear()
            await callback.message.answer(str(error))
            return
        except SQLAlchemyError:
            await session.rollback()
            await callback.message.answer("Не вдалося зберегти розклад. Спробуйте підтвердити ще раз.")
            return
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Щотижневий розклад збережено.",
                                  reply_markup=student_schedule_keyboard(data["student_id"]))


@router.callback_query(F.data.startswith("schedule_day_") |
                       F.data.startswith("schedule_duration_") | (F.data == "schedule_confirm"))
async def stale_schedule_button(callback):
    await callback.answer("Ця кнопка вже неактивна. Відкрийте розклад учня знову.", show_alert=True)
