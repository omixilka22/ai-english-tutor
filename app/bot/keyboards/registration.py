from app.bot.ui import keyboard


def registration_keyboard():
    return keyboard([[('👨‍🏫 Викладач', 'register_teacher'), ('🎓 Учень', 'register_student')]])


def role_change_keyboard():
    return keyboard([
        [('👨‍🏫 Стати викладачем', 'change_to_teacher')],
        [('🎓 Стати учнем', 'change_to_student')],
        [('‹ Назад', 'home')],
    ])
