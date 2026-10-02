from app.bot.ui import keyboard, navigation


def teacher_main_menu_keyboard():
    return keyboard([
        [('👥 Мої учні', 'my_students'), ('📅 Розклад', 'schedule_menu')],
        [('＋ Запросити учня', 'create_student_invite')],
        [('⚙ Змінити роль', 'change_role')],
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
        [('🎥 Посилання на урок', f'meet_{student_id}')],
        [('📅 Розклад', f'student_schedule_{student_id}')],
        [('📚 Заняття', f'student_lessons_{student_id}')],
        [('📖 Матеріали уроків', f'materials_{student_id}')],
        [('＋ Додаткове заняття', f'extra_lesson_{student_id}')],
        [('‹ До учнів', 'my_students'), ('⌂ Головне меню', 'home')],
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