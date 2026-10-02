"""One tracked, disposable analysis notice per teacher; student files are permanent."""
import asyncio
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select
from app.database.models import User, UserRole
from app.database.database import AsyncSessionLocal


async def publish_notice(session, bot, teacher, text, markup):
    # Serialize notices from concurrent lesson workers for this teacher.
    await session.refresh(teacher, with_for_update=True)
    old_id = getattr(teacher, 'material_notice_id', None)
    if old_id:
        try:
            await bot.edit_message_text(chat_id=teacher.telegram_id, message_id=old_id,
                                        text=text, reply_markup=markup)
            return
        except TelegramBadRequest as error:
            if 'message is not modified' in error.message.lower():
                return
            # A deleted/expired notice can be replaced. Delete the old one if possible.
            try:
                await bot.delete_message(chat_id=teacher.telegram_id, message_id=old_id)
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
    message = await bot.send_message(chat_id=teacher.telegram_id, text=text, reply_markup=markup)
    teacher.material_notice_id = message.message_id


async def clean_notice(event):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == event.from_user.id)
                                      .with_for_update())).scalar_one_or_none()
        if user is None or user.role != UserRole.TEACHER:
            return
        ids = set()
        if user.material_notice_id:
            ids.add(user.material_notice_id)
        # Older versions did not store IDs. Clicking an old notice identifies it safely.
        callback_data = getattr(event, 'data', None)
        message = getattr(event, 'message', None)
        if (callback_data and callback_data.startswith('notification_material_') and message
                and not getattr(message, 'document', None)):
            ids.add(message.message_id)
        for message_id in ids:
            try:
                await asyncio.wait_for(event.bot.delete_message(chat_id=event.from_user.id,
                                                                 message_id=message_id), timeout=5)
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
        user.material_notice_id = None
        await session.commit()
