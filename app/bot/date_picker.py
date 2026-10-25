"""Date buttons shared by one-off lesson creation and rescheduling."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import F
from app.bot.ui import keyboard, show_screen
from app.services.calendar_service import utcnow

DAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд')


def date_rows(zone, offset=0):
    today = utcnow().astimezone(ZoneInfo(zone)).date()
    buttons = []
    for n in range(offset, offset + 14):
        day = today + timedelta(days=n)
        label = 'Сьогодні' if n == 0 else 'Завтра' if n == 1 else DAYS[day.weekday()]
        buttons.append((f'{label} {day:%d.%m}', f'pickdate_{day.isoformat()}'))
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    nav = []
    if offset:
        nav.append(('‹ Раніше', f'pickdays_{max(0, offset-14)}'))
    nav.append(('Пізніше ›', f'pickdays_{offset+14}'))
    return rows + [nav]


def date_text(raw, data):
    raw = (raw or '').strip()
    if data.get('picked_date') and len(raw) <= 5:
        day = datetime.fromisoformat(data['picked_date'])
        return f'{day:%d.%m.%Y} {raw}'
    return raw


def bind_picker(router, active_state, submit, zone_for, back_for):
    @router.callback_query(active_state, F.data.startswith('pickdays_'))
    async def days(callback, state):
        await callback.answer()
        data = await state.get_data()
        try:
            offset = int(callback.data.rsplit('_', 1)[1])
            if offset < 0 or offset > 3640:
                raise ValueError()
        except ValueError:
            return
        await state.update_data(picked_date=None)
        await show_screen(callback, state, 'Оберіть дату заняття:', reply_markup=keyboard(
            date_rows(zone_for(data), offset) + [[('‹ Назад', back_for(data)), ('⌂ Меню', 'home')]]))

    @router.callback_query(active_state, F.data.startswith('pickdate_'))
    async def day(callback, state):
        await callback.answer()
        data = await state.get_data()
        try:
            chosen = datetime.strptime(callback.data.removeprefix('pickdate_'), '%Y-%m-%d').date()
            if chosen < utcnow().astimezone(ZoneInfo(zone_for(data))).date():
                raise ValueError()
        except ValueError:
            await show_screen(callback, state, 'Оберіть актуальну дату.', reply_markup=keyboard(date_rows(zone_for(data))))
            return
        await state.update_data(picked_date=chosen.isoformat())
        rows = [[(f'{h}:00', f'picktime_{h}:00'), (f'{h}:30', f'picktime_{h}:30')] for h in (9, 12, 15, 18, 19, 20)]
        rows += [[('‹ Інша дата', 'pickdays_0')], [('Скасувати', back_for(data))]]
        await show_screen(callback, state, f'{chosen:%d.%m.%Y} · {zone_for(data)}\n\nОберіть час або напишіть свій, наприклад 17:20.', reply_markup=keyboard(rows))

    @router.callback_query(active_state, F.data.startswith('picktime_'))
    async def time(callback, state):
        await callback.answer()
        data = await state.get_data()
        if not data.get('picked_date'):
            return
        await submit(callback, state, callback.data.removeprefix('picktime_'))
