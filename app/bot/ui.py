"""A single editable navigation message per conversation, with bounded pages."""
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def keyboard(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
        for row in rows
    ])


def navigation(back='home'):
    rows = [[('‹ Назад', back)]]
    if back != 'home':
        rows.append([('⌂ Головне меню', 'home')])
    return keyboard(rows)


async def clear_flow(state):
    """Reset business input, retaining only the active navigation message ID."""
    screen = (await state.get_data()).get('_screen_id')
    await state.clear()
    if screen is not None:
        await state.update_data(_screen_id=screen)


async def delete_input(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        # Old messages or missing deletion rights must not break navigation.
        logger.debug('Could not delete a navigation/input message', exc_info=True)


async def show_screen(event, state, text, reply_markup=None):
    """Edit the current screen; replace it only if Telegram cannot edit it."""
    callback = isinstance(event, CallbackQuery)
    message = event.message if callback else event
    bot = event.bot
    chat_id = message.chat.id
    data = await state.get_data()
    old_id = data.get('_screen_id')
    command = (message.text or '').split(maxsplit=1)[0].split('@', 1)[0].lower() if not callback and message.text else ''
    navigation_command = command in {'/start', '/menu', '/cancel'}
    from_notification = callback and (event.data == 'notification_list' or event.data.startswith(('notification_lesson_', 'notification_meet_')))
    screen_id = old_id if from_notification else (message.message_id if callback else old_id)
    if navigation_command:
        # A command is a visible entry point: answer at the bottom, even if an old menu exists.
        screen_id = None
    markup = reply_markup if reply_markup is not None else navigation()
    if callback and not from_notification and old_id and old_id != screen_id:
        await delete_input(bot, chat_id, old_id)
    if not callback and not navigation_command:
        # Only delete the input being handled; never sweep chat history.
        await delete_input(bot, chat_id, message.message_id)
    if screen_id:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=screen_id,
                                        text=text, reply_markup=markup)
            await state.update_data(_screen_id=screen_id)
            return
        except TelegramBadRequest as error:
            if 'message is not modified' in error.message.lower():
                await state.update_data(_screen_id=screen_id)
                return
            # Deleted/old/inaccessible screen: create a usable replacement.
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    await state.update_data(_screen_id=sent.message_id)
    replaced_id = old_id if navigation_command else screen_id
    if replaced_id and replaced_id != sent.message_id:
        await delete_input(bot, chat_id, replaced_id)


async def paginated_screen(event, state, title, *, lines=None, rows=None, footer=None):
    """Store short-lived view pages; entering another screen resets them."""
    entries = lines if lines is not None else rows
    entries = entries or []
    pages = []
    for offset in range(0, max(1, len(entries)), 8):
        portion = entries[offset:offset + 8]
        text = title
        if lines is not None:
            text += '\n\n' + '\n'.join(str(line)[:320] for line in portion)
        pages.append({'text':text,'rows':portion if rows is not None else []})
    await state.update_data(_pages=pages, _page_footer=(footer or navigation()).model_dump())
    await show_page(event, state, 0)


async def show_page(event, state, index):
    data = await state.get_data()
    pages = data.get('_pages', [])
    if not pages:
        await show_screen(event, state, 'Цей список уже закрито. Поверніться в головне меню.')
        return
    index = min(max(index, 0), len(pages) - 1)
    page = pages[index]
    markup = keyboard(page['rows'])
    if len(pages) > 1:
        arrows = []
        if index:
            arrows.append(InlineKeyboardButton(text='‹ Попередня', callback_data=f'ui_page_{index - 1}'))
        if index + 1 < len(pages):
            arrows.append(InlineKeyboardButton(text='Наступна ›', callback_data=f'ui_page_{index + 1}'))
        markup.inline_keyboard.append(arrows)
    footer = InlineKeyboardMarkup.model_validate(data['_page_footer'])
    markup.inline_keyboard.extend(footer.inline_keyboard)
    text = page['text']
    if len(pages) > 1:
        text += f'\n\nСторінка {index + 1} / {len(pages)}'
    await show_screen(event, state, text, reply_markup=markup)
