"""Durable Sunday renewal prompts; no automatic lesson publication."""
import asyncio
import logging
from datetime import timedelta
from sqlalchemy import select
from app.database.database import AsyncSessionLocal
from app.database.models import Teacher, User, UserRole, WeekRenewal
from app.services.calendar_service import utcnow
from app.services.week_service import renewal_target, week_lessons, decision_row
from app.bot.ui import keyboard

logger = logging.getLogger(__name__)


def renewal_keyboard(week):
    stamp = week.isoformat()
    return keyboard([
        [('✓ Повторити розклад', f'week_repeat_{stamp}')],
        [('Скласти новий', f'week_new_{stamp}')],
        [('Переглянути тиждень', f'week_view_{stamp}')],
        [('⌂ Головне меню', 'home')],
    ])


async def tick(bot, now=None):
    now = now or utcnow()
    target = renewal_target(now)
    async with AsyncSessionLocal() as session:
        teachers = list((await session.execute(select(Teacher.id, User.telegram_id)
            .join(User, Teacher.user_id == User.id).where(User.role == UserRole.TEACHER))).all())
    for teacher_id, chat_id in teachers:
        try:
            async with AsyncSessionLocal() as session:
                # Serialize with manual creation and repeated worker ticks.
                await session.execute(select(Teacher).where(Teacher.id == teacher_id).with_for_update())
                source = await week_lessons(session, teacher_id, target - timedelta(days=7))
                if not any(l.schedule_id is not None for l in source):
                    continue
                row = await decision_row(session, teacher_id, target)
                if row.decision != 'pending' or row.message_id is not None:
                    continue
                sent = await bot.send_message(chat_id,
                    f'📅 Розклад на {target:%d.%m}–{target + timedelta(days=6):%d.%m}\n\n'
                    'Повторити дні й час попереднього тижня чи скласти новий розклад?\n'
                    'Додаткові та скасовані уроки не копіюються. Без вашої відповіді нові заняття не створюються.',
                    reply_markup=renewal_keyboard(target), request_timeout=15)
                row.message_id = sent.message_id
                await session.commit()
        except Exception as error:
            # Telegram timeout may have delivered a message; actions are still idempotent.
            logger.warning('Week prompt failed for teacher %s: %s', teacher_id, type(error).__name__)


async def run(bot):
    while True:
        try:
            await tick(bot)
        except Exception as error:
            logger.warning('Weekly planning unavailable: %s', type(error).__name__)
        await asyncio.sleep(60)
