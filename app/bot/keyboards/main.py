from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def teacher_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨‍🎓 Мої учні",
                    callback_data="my_students",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👨‍🎓 Запросити учня",
                    callback_data="create_student_invite",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Розклад",
                    callback_data="schedule_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Змінити роль",
                    callback_data="change_role",
                )
            ],
        ]
    )


def student_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Змінити роль",
                    callback_data="change_role",
                )
            ],
        ]
    )


def schedule_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Загальний розклад",
                    callback_data="general_schedule",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👨‍🎓 Розклад учня",
                    callback_data="student_schedule",
                )
            ],
        ]
    )


def students_keyboard(students) -> InlineKeyboardMarkup:
    buttons = []

    for student in students:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"👨‍🎓 {student.user.name}",
                    callback_data=f"student_{student.id}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def students_keyboard(students) -> InlineKeyboardMarkup:
    buttons = []

    for student, user in students:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"👨‍🎓 {user.name}",
                    callback_data=f"student_{student.id}",
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

def student_menu_keyboard(student_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Розклад",
                    callback_data=f"student_schedule_{student_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Заняття",
                    callback_data=f"student_lessons_{student_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад до учнів",
                    callback_data="my_students",
                )
            ],
        ]
    )