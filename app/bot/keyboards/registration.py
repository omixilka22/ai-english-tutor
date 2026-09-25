from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def registration_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨‍🏫 Teacher",
                    callback_data="register_teacher",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👨‍🎓 Student",
                    callback_data="register_student",
                )
            ],
        ]
    )

def role_change_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨‍🏫 Стати Teacher",
                    callback_data="change_to_teacher",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👨‍🎓 Стати Student",
                    callback_data="change_to_student",
                )
            ],
        ]
    )