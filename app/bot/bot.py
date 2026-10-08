import asyncio
from app.bot.handlers.materials import router as materials_router
from app.workers.materials import run as run_materials
from app.workers.notifications import run as run_notifications
from app.bot.handlers.notification_settings import router as notifications_router
from contextlib import suppress
from app.workers.week_renewal import run as run_week_renewal
from app.bot.handlers.lessons import router as lesson_router

from aiogram import Bot, Dispatcher, F
from aiogram.types import BotCommand, MenuButtonCommands
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import SimpleEventIsolation

from app.config import settings
from app.bot.handlers.schedules import router as schedule_router, teacher_for, owned_student
from app.bot.keyboards.main import teacher_main_menu_keyboard, student_main_menu_keyboard, student_menu_keyboard
from app.bot.keyboards.registration import registration_keyboard, role_change_keyboard
from app.bot.states.registration import RegistrationState
from app.bot.ui import clear_flow, show_screen, show_page, navigation, paginated_screen
from app.database.database import AsyncSessionLocal
from app.database.models import UserRole
from app.services.registration_service import RegistrationService
from app.services.user_service import UserService
from app.services.student_service import StudentService
from app.services.invite_service import InviteService

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(events_isolation=SimpleEventIsolation())
dp.include_router(schedule_router)
dp.include_router(lesson_router)
dp.include_router(notifications_router)
from app.bot.handlers.meeting import router as meeting_router
dp.include_router(meeting_router)
from app.bot.handlers.student_removal import router as student_removal_router
dp.include_router(student_removal_router)
dp.include_router(materials_router)


async def show_home(event, state, note=''):
    await clear_flow(state)
    async with AsyncSessionLocal() as session:
        user = await UserService.get_by_telegram_id(session, event.from_user.id)
    prefix = f'{note}\n\n' if note else ''
    if user is None:
        text = 'AI English Tutor\n\nПомічник для ваших занять англійською.\nОберіть свою роль:'
        markup = registration_keyboard()
    elif user.role == UserRole.TEACHER:
        text = f'👨‍🏫 Кабінет викладача\n\nВітаю, {user.name}!\nУчні та розклад — усе під рукою.'
        markup = teacher_main_menu_keyboard()
    else:
        text = f'🎓 Кабінет учня\n\nВітаю, {user.name}!\nТут з’являтимуться ваші навчальні матеріали.'
        markup = student_main_menu_keyboard()
    await show_screen(event, state, prefix + text, reply_markup=markup)


@dp.message(CommandStart())
async def start_handler(message, command: CommandObject, state: FSMContext):
    await clear_flow(state)
    note = ''
    if command.args:
        async with AsyncSessionLocal() as session:
            try:
                invite = await InviteService.validate_invite(session, command.args)
                user = await UserService.get_by_telegram_id(session, message.from_user.id)
                if user is None:
                    user = await RegistrationService.register_student(
                        session=session, telegram_id=message.from_user.id, name=message.from_user.full_name)
                if user.role != UserRole.STUDENT:
                    raise ValueError('Це запрошення призначене для учня.')
                student = await StudentService.get_by_user_id(session, user.id)
                if student is None:
                    raise ValueError('Профіль учня не знайдено.')
                await InviteService.use_invite(session=session, invite=invite, student=student)
                note = '✓ Ви успішно приєдналися до викладача.'
            except ValueError as error:
                note = f'Не вдалося прийняти запрошення: {error}'
    await show_home(message, state, note)


@dp.message(Command('cancel', 'menu'))
async def menu_command(message, state: FSMContext):
    await show_home(message, state)


@dp.callback_query(F.data == 'home')
async def home_callback(callback, state: FSMContext):
    await callback.answer()
    await show_home(callback, state)


@dp.callback_query(F.data.regexp(r'^ui_page_\d+$'))
async def page_callback(callback, state: FSMContext):
    await callback.answer()
    await show_page(callback, state, int(callback.data.rsplit('_',1)[1]))


@dp.callback_query(F.data == 'register_teacher')
async def teacher_registration_callback(callback, state: FSMContext):
    await clear_flow(state)
    await state.set_state(RegistrationState.waiting_for_teacher_code)
    await callback.answer()
    await show_screen(callback, state, '👨‍🏫 Реєстрація викладача\n\nВведіть код доступу.',
                      reply_markup=navigation())


@dp.callback_query(F.data == 'change_to_teacher')
async def change_to_teacher_callback(callback, state: FSMContext):
    await clear_flow(state)
    await state.set_state(RegistrationState.waiting_for_teacher_code_change)
    await callback.answer()
    await show_screen(callback, state, '👨‍🏫 Зміна ролі\n\nВведіть код доступу викладача.',
                      reply_markup=navigation('change_role'))


@dp.message(RegistrationState.waiting_for_teacher_code)
@dp.message(RegistrationState.waiting_for_teacher_code_change)
async def teacher_code_handler(message, state: FSMContext):
    changing = await state.get_state() == RegistrationState.waiting_for_teacher_code_change.state
    back = 'change_role' if changing else 'home'
    if message.text != settings.TEACHER_REGISTRATION_CODE:
        await show_screen(message, state, 'Код не підходить.\n\nСпробуйте ще раз або поверніться назад.',
                          reply_markup=navigation(back))
        return
    async with AsyncSessionLocal() as session:
        try:
            if changing:
                await RegistrationService.change_role(session=session, telegram_id=message.from_user.id,
                                                      new_role=UserRole.TEACHER)
            else:
                await RegistrationService.register_teacher(session=session, telegram_id=message.from_user.id,
                                                           name=message.from_user.full_name)
        except ValueError as error:
            await show_screen(message, state, str(error), reply_markup=navigation(back))
            return
    await show_home(message, state, '✓ Ви зареєстровані як викладач.' if not changing else '✓ Роль змінено.')


@dp.callback_query(F.data == 'register_student')
async def student_registration_callback(callback, state: FSMContext):
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            await RegistrationService.register_student(session=session, telegram_id=callback.from_user.id,
                                                       name=callback.from_user.full_name)
            note = '✓ Реєстрацію завершено.'
        except ValueError as error:
            note = str(error)
    await show_home(callback, state, note)


@dp.callback_query(F.data == 'change_role')
async def change_role_callback(callback, state: FSMContext):
    await clear_flow(state)
    await callback.answer()
    await show_screen(callback, state, '⚙ Роль у боті\n\nОберіть, як хочете користуватися ботом.',
                      reply_markup=role_change_keyboard())


@dp.callback_query(F.data == 'change_to_student')
async def change_to_student_callback(callback, state: FSMContext):
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            await RegistrationService.change_role(session=session, telegram_id=callback.from_user.id,
                                                  new_role=UserRole.STUDENT)
            note = '✓ Роль змінено.'
        except ValueError as error:
            note = str(error)
    await show_home(callback, state, note)


@dp.callback_query(F.data == 'create_student_invite')
async def create_student_invite_callback(callback, state: FSMContext):
    await clear_flow(state)
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            invite = await InviteService.create_invite(session=session, teacher_id=teacher.id)
        except ValueError as error:
            await show_screen(callback, state, str(error))
            return
    info = await callback.bot.get_me()
    await show_screen(callback, state,
        '＋ Запрошення для учня\n\nСкопіюйте посилання й надішліть учню:\n'
        f'https://t.me/{info.username}?start={invite.token}\n\n'
        'Посилання діє 24 години й доступне для одного використання.',
        reply_markup=navigation())


@dp.callback_query(F.data == 'my_students')
async def my_students_callback(callback, state: FSMContext):
    await clear_flow(state)
    await callback.answer()
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
        except ValueError as error:
            await show_screen(callback, state, str(error))
            return
        students = await StudentService.get_by_teacher_id(session, teacher.id)
    if not students:
        await show_screen(callback, state, '👥 Мої учні\n\nПоки що порожньо. Запросіть першого учня.',
                          reply_markup=teacher_main_menu_keyboard())
        return
    await paginated_screen(callback, state, f'👥 Мої учні · {len(students)}\n\nОберіть учня:',
        rows=[[(user.name, f'student_{student.id}')] for student, user in students], footer=navigation())


@dp.callback_query(F.data.regexp(r'^student_\d+$'))
async def student_callback(callback, state: FSMContext):
    await clear_flow(state)
    await callback.answer()
    student_id = int(callback.data.rsplit('_',1)[1])
    async with AsyncSessionLocal() as session:
        try:
            teacher = await teacher_for(session, callback.from_user.id)
            student = await owned_student(session, teacher.id, student_id)
        except ValueError as error:
            await show_screen(callback, state, str(error), reply_markup=navigation('my_students'))
            return
        user = await UserService.get_by_id(session, student.user_id)
    await show_screen(callback, state, f'👤 {user.name if user else "Учень"}\n\nРозклад і заняття учня.',
                      reply_markup=student_menu_keyboard(student_id))


async def configure_navigation(client):
    await client.set_my_commands([
        BotCommand(command='start', description='Відкрити бота'),
        BotCommand(command='menu', description='Головне меню'),
        BotCommand(command='cancel', description='Скасувати поточну дію'),
    ])
    await client.set_chat_menu_button(menu_button=MenuButtonCommands())


async def main():
    from app.bot.ui import set_material_notice_cleanup
    from app.services.material_notices import clean_notice
    set_material_notice_cleanup(clean_notice)
    await configure_navigation(bot)
    generator = asyncio.create_task(run_week_renewal(bot))
    notifications = asyncio.create_task(run_notifications(bot))
    materials = asyncio.create_task(run_materials(bot))
    try:
        await dp.start_polling(bot)
    finally:
        generator.cancel()
        notifications.cancel()
        materials.cancel()
        for task in (generator, notifications, materials):
            with suppress(asyncio.CancelledError):
                await task


if __name__ == '__main__':
    asyncio.run(main())
