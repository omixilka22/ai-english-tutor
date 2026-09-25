import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.config import settings

from app.bot.keyboards.registration import (
    registration_keyboard,
    role_change_keyboard,
)

from app.bot.keyboards.main import (
    teacher_main_menu_keyboard,
    student_main_menu_keyboard,
    schedule_menu_keyboard,
    students_keyboard,
    student_menu_keyboard,
)

from app.bot.states.registration import RegistrationState

from app.database.database import AsyncSessionLocal
from app.database.models import UserRole

from app.services.registration_service import RegistrationService
from app.services.user_service import UserService
from app.services.teacher_service import TeacherService
from app.services.student_service import StudentService
from app.services.invite_service import InviteService


bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(
    message: Message,
    command: CommandObject,
):
    telegram_id = message.from_user.id
    name = message.from_user.full_name

    # =========================================================
    # /start TOKEN
    # =========================================================

    if command.args:
        token = command.args

        async with AsyncSessionLocal() as session:
            try:
                # 1. Перевіряємо invite
                invite = await InviteService.validate_invite(
                    session,
                    token,
                )

                # 2. Перевіряємо користувача
                user = await UserService.get_by_telegram_id(
                    session,
                    telegram_id,
                )

                # 3. Якщо користувача ще немає —
                # створюємо Student
                if user is None:
                    user = await RegistrationService.register_student(
                        session=session,
                        telegram_id=telegram_id,
                        name=name,
                    )

                    await message.answer(
                        f"👋 Привіт, {name}!\n\n"
                        "Я AI English Tutor — помічник для роботи "
                        "вчителя та учня англійської мови.\n\n"
                        "Ви автоматично зареєстровані як Student, "
                        "оскільки перейшли за запрошенням Teacher. 🎓"
                    )

                # 4. Invite призначений тільки для Student
                if user.role != UserRole.STUDENT:
                    await message.answer(
                        "Це запрошення призначене для Student."
                    )
                    return

                # 5. Знаходимо Student profile
                student = await StudentService.get_by_user_id(
                    session,
                    user.id,
                )

                if student is None:
                    await message.answer(
                        "Профіль Student не знайдено."
                    )
                    return

                # 6. Прив'язуємо Student до Teacher
                await InviteService.use_invite(
                    session=session,
                    invite=invite,
                    student=student,
                )

                await message.answer(
                    "Ви успішно приєдналися до Teacher! 🎓\n\n"
                    "Тепер ваш Teacher може бачити вас у своїх учнях.",
                    reply_markup=student_main_menu_keyboard(),
                )

            except ValueError as error:
                await message.answer(
                    f"Не вдалося прийняти запрошення: {error}"
                )

        return

    # =========================================================
    # Звичайний /start
    # =========================================================

    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(
            session,
            telegram_id,
        )

    if user is not None:

        if user.role == UserRole.STUDENT:
            await message.answer(
                f"👋 Привіт, {name}!\n\n"
                "Ви вже зареєстровані як Student. 🎓\n\n"
                "Оберіть потрібну дію:",
                reply_markup=student_main_menu_keyboard(),
            )
            return

        if user.role == UserRole.TEACHER:
            await message.answer(
                f"👋 Привіт, {name}!\n\n"
                "Ви вже зареєстровані як Teacher. 👨‍🏫\n\n"
                "Оберіть потрібну дію:",
                reply_markup=teacher_main_menu_keyboard(),
            )
            return

    # Новий користувач
    await message.answer(
        f"👋 Привіт, {name}!\n\n"
        "Я AI English Tutor — помічник для роботи "
        "вчителя та учня англійської мови.\n\n"
        "Щоб почати роботу, оберіть вашу роль:",
        reply_markup=registration_keyboard(),
    )


# =============================================================
# REGISTRATION
# =============================================================

@dp.callback_query(F.data == "register_teacher")
async def teacher_registration_callback(
    callback,
    state: FSMContext,
):
    await state.set_state(
        RegistrationState.waiting_for_teacher_code
    )

    await callback.message.answer(
        "Введіть код реєстрації Teacher:"
    )

    await callback.answer()


@dp.message(RegistrationState.waiting_for_teacher_code)
async def teacher_code_handler(
    message: Message,
    state: FSMContext,
):
    code = message.text

    if code != settings.TEACHER_REGISTRATION_CODE:
        await message.answer(
            "Невірний код реєстрації. Спробуйте ще раз."
        )
        return

    telegram_id = message.from_user.id
    name = message.from_user.full_name

    async with AsyncSessionLocal() as session:
        try:
            await RegistrationService.register_teacher(
                session=session,
                telegram_id=telegram_id,
                name=name,
            )

            await message.answer(
                f"Реєстрація Teacher успішна, {name}! 👨‍🏫\n\n"
                "Тепер ви зареєстровані як Teacher.",
                reply_markup=teacher_main_menu_keyboard(),
            )

        except ValueError as error:
            await message.answer(
                f"Не вдалося зареєструватися: {error}"
            )
            return

    await state.clear()


@dp.callback_query(F.data == "register_student")
async def student_registration_callback(callback):
    telegram_id = callback.from_user.id
    name = callback.from_user.full_name

    async with AsyncSessionLocal() as session:
        try:
            await RegistrationService.register_student(
                session=session,
                telegram_id=telegram_id,
                name=name,
            )

            await callback.message.edit_reply_markup(
                reply_markup=None
            )

            await callback.message.answer(
                f"Реєстрація успішна, {name}! 🎓\n\n"
                "Тепер ви зареєстровані як Student.",
                reply_markup=student_main_menu_keyboard(),
            )

        except ValueError as error:
            await callback.message.answer(
                f"Не вдалося зареєструватися: {error}"
            )

    await callback.answer()


# =============================================================
# ROLE CHANGE
# =============================================================

@dp.callback_query(F.data == "change_role")
async def change_role_callback(callback):
    await callback.message.answer(
        "Оберіть нову роль:",
        reply_markup=role_change_keyboard(),
    )

    await callback.answer()


@dp.callback_query(F.data == "change_to_teacher")
async def change_to_teacher_callback(
    callback,
    state: FSMContext,
):
    await state.set_state(
        RegistrationState.waiting_for_teacher_code_change
    )

    await callback.message.answer(
        "Для зміни ролі на Teacher введіть код реєстрації:"
    )

    await callback.answer()


@dp.message(RegistrationState.waiting_for_teacher_code_change)
async def teacher_code_change_handler(
    message: Message,
    state: FSMContext,
):
    code = message.text

    if code != settings.TEACHER_REGISTRATION_CODE:
        await message.answer(
            "Невірний код реєстрації. Спробуйте ще раз."
        )
        return

    telegram_id = message.from_user.id
    name = message.from_user.full_name

    async with AsyncSessionLocal() as session:
        try:
            await RegistrationService.change_role(
                session=session,
                telegram_id=telegram_id,
                new_role=UserRole.TEACHER,
            )

            await message.answer(
                f"Роль змінено, {name}! 👨‍🏫\n\n"
                "Тепер ви Teacher.",
                reply_markup=teacher_main_menu_keyboard(),
            )

        except ValueError as error:
            await message.answer(
                f"Не вдалося змінити роль: {error}"
            )
            return

    await state.clear()


@dp.callback_query(F.data == "change_to_student")
async def change_to_student_callback(callback):
    telegram_id = callback.from_user.id
    name = callback.from_user.full_name

    async with AsyncSessionLocal() as session:
        try:
            await RegistrationService.change_role(
                session=session,
                telegram_id=telegram_id,
                new_role=UserRole.STUDENT,
            )

            await callback.message.answer(
                f"Роль змінено, {name}! 🎓\n\n"
                "Тепер ви Student.",
                reply_markup=student_main_menu_keyboard(),
            )

        except ValueError as error:
            await callback.message.answer(
                f"Не вдалося змінити роль: {error}"
            )

    await callback.answer()


# =============================================================
# TEACHER → INVITE STUDENT
# =============================================================

@dp.callback_query(F.data == "create_student_invite")
async def create_student_invite_callback(callback):
    telegram_id = callback.from_user.id

    async with AsyncSessionLocal() as session:

        user = await UserService.get_by_telegram_id(
            session,
            telegram_id,
        )

        if user is None:
            await callback.message.answer(
                "Ви ще не зареєстровані."
            )
            await callback.answer()
            return

        if user.role != UserRole.TEACHER:
            await callback.message.answer(
                "Тільки Teacher може створювати запрошення для учнів."
            )
            await callback.answer()
            return

        teacher = await TeacherService.get_by_user_id(
            session,
            user.id,
        )

        if teacher is None:
            await callback.message.answer(
                "Профіль Teacher не знайдено."
            )
            await callback.answer()
            return

        invite = await InviteService.create_invite(
            session=session,
            teacher_id=teacher.id,
        )

        bot_info = await bot.get_me()

        invite_link = (
            f"https://t.me/{bot_info.username}"
            f"?start={invite.token}"
        )

        await callback.message.answer(
            "Запрошення для учня створено! 👨‍🎓\n\n"
            "Надішліть це посилання учню:\n"
            f"{invite_link}"
        )

    await callback.answer()


# =============================================================
# TEACHER → MY STUDENTS
# =============================================================

@dp.callback_query(F.data == "my_students")
async def my_students_callback(callback):
    telegram_id = callback.from_user.id

    async with AsyncSessionLocal() as session:

        # 1. Знаходимо User
        user = await UserService.get_by_telegram_id(
            session,
            telegram_id,
        )

        if user is None:
            await callback.message.answer(
                "Ви ще не зареєстровані."
            )
            await callback.answer()
            return

        # 2. Перевіряємо роль
        if user.role != UserRole.TEACHER:
            await callback.message.answer(
                "Тільки Teacher може переглядати список учнів."
            )
            await callback.answer()
            return

        # 3. Знаходимо Teacher profile
        teacher = await TeacherService.get_by_user_id(
            session,
            user.id,
        )

        if teacher is None:
            await callback.message.answer(
                "Профіль Teacher не знайдено."
            )
            await callback.answer()
            return

        # 4. Отримуємо учнів цього Teacher
        students = await StudentService.get_by_teacher_id(
            session,
            teacher.id,
        )

        # 5. Якщо учнів немає
        if not students:
            await callback.message.answer(
                "👨‍🎓 У вас поки немає учнів.\n\n"
                "Запросіть учня через кнопку "
                "«Запросити учня»."
            )
            await callback.answer()
            return

        # 6. Показуємо список учнів
        await callback.message.answer(
            "👨‍🎓 Ваші учні:\n\n"
            "Оберіть учня:",
            reply_markup=students_keyboard(students),
        )

    await callback.answer()

# =============================================================
# TEACHER → STUDENT
# =============================================================

@dp.callback_query(
    F.data.startswith("student_") &
    F.data.regexp(r"^student_\d+$")
)
async def student_callback(callback):
    student_id = int(callback.data.split("_")[1])
    telegram_id = callback.from_user.id

    async with AsyncSessionLocal() as session:

        # 1. Знаходимо User
        user = await UserService.get_by_telegram_id(
            session,
            telegram_id,
        )

        if user is None:
            await callback.message.answer(
                "Ви ще не зареєстровані."
            )
            await callback.answer()
            return

        # 2. Перевіряємо роль
        if user.role != UserRole.TEACHER:
            await callback.message.answer(
                "Тільки Teacher може переглядати учнів."
            )
            await callback.answer()
            return

        # 3. Знаходимо Teacher
        teacher = await TeacherService.get_by_user_id(
            session,
            user.id,
        )

        if teacher is None:
            await callback.message.answer(
                "Профіль Teacher не знайдено."
            )
            await callback.answer()
            return

        # 4. Знаходимо Student
        student = await StudentService.get_by_id(
            session,
            student_id,
        )

        if student is None:
            await callback.message.answer(
                "Учня не знайдено."
            )
            await callback.answer()
            return

        # 5. Перевіряємо, що цей Student належить саме цьому Teacher
        if student.teacher_id != teacher.id:
            await callback.message.answer(
                "Цей учень не належить вам."
            )
            await callback.answer()
            return

        # 6. Отримуємо User учня
        student_user = await UserService.get_by_id(
            session,
            student.user_id,
        )

        if student_user is None:
            await callback.message.answer(
                "Користувача учня не знайдено."
            )
            await callback.answer()
            return

        # 7. Показуємо меню учня
        await callback.message.answer(
            f"👨‍🎓 {student_user.name}\n\n"
            "Оберіть потрібну дію:",
            reply_markup=student_menu_keyboard(student.id),
        )

    await callback.answer()


# =============================================================
# SCHEDULE
# =============================================================

@dp.callback_query(F.data == "schedule_menu")
async def schedule_menu_callback(callback):

    await callback.message.answer(
        "📅 Розклад\n\n"
        "Оберіть, що хочете переглянути:",
        reply_markup=schedule_menu_keyboard(),
    )

    await callback.answer()


@dp.callback_query(F.data == "general_schedule")
async def general_schedule_callback(callback):

    await callback.message.answer(
        "📅 Загальний розклад\n\n"
        "Тут буде розклад усіх ваших учнів."
    )

    await callback.answer()


@dp.callback_query(F.data == "student_schedule")
async def student_schedule_callback(callback):

    await callback.message.answer(
        "👨‍🎓 Розклад учня\n\n"
        "Тут ви зможете вибрати учня "
        "та переглянути його розклад."
    )

    await callback.answer()


# =============================================================
# START BOT
# =============================================================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())