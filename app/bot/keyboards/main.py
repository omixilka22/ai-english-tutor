from app.bot.ui import keyboard, navigation


def teacher_main_menu_keyboard():
    return keyboard([
        [('📅 Розклад', 'general_schedule'), ('👥 Учні', 'my_students')],
        [('⚙ Налаштування', 'teacher_settings')],
    ])


def student_main_menu_keyboard():
    return keyboard([[('📚 Мої заняття', 'my_lessons')], [('📖 Матеріали уроків', 'my_materials')], [('🔔 Нагадування', 'notification_settings')]])


def schedule_menu_keyboard():
    return keyboard([
        [('📅 Увесь розклад', 'general_schedule')],
        [('👤 Обрати учня', 'student_schedule')],
        [('‹ Назад', 'home')],
    ])


def students_keyboard(students):
    return keyboard([[(user.name, f'student_{student.id}')] for student, user in students]
                    + [[('‹ Назад', 'home')]])


def student_menu_keyboard(student_id):
    return keyboard([
        [('📅 Заняття', f'student_schedule_{student_id}')],
        [('📖 Матеріали', f'materials_{student_id}')],
        [('⚙ Налаштування учня', f'student_settings_{student_id}')],
        [('‹ До учнів', 'my_students'), ('⌂ Меню', 'home')],
    ])


def student_schedule_keyboard(student_id):
    return keyboard([
        [('＋ Додати розклад', f'add_schedule_{student_id}')],
        [('✎ Перенести / скасувати заняття', f'student_lessons_{student_id}')],
        [('＋ Додаткове заняття', f'extra_lesson_{student_id}')],
        [('‹ До учня', f'student_{student_id}'), ('⌂ Головне меню', 'home')],
    ])


def weekdays_keyboard():
    days = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд')
    return keyboard([[(name, f'schedule_day_{i}') for i, name in enumerate(days[:4])],
                     [(days[i], f'schedule_day_{i}') for i in range(4,7)]])