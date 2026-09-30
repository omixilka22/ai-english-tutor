"""Maintain a rolling four-week calendar while the bot process is running."""
import asyncio
import logging
from sqlalchemy import select
from app.database.database import AsyncSessionLocal
from app.database.models import WeeklySchedule
from app.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)


async def generate_all():
    async with AsyncSessionLocal() as session:
        ids = (await session.execute(select(WeeklySchedule.student_id)
            .where(WeeklySchedule.active.is_(True)).distinct())).scalars().all()
    for student_id in ids:
        try:
            async with AsyncSessionLocal() as session:
                await CalendarService.generate_for_student(session,student_id)
        except Exception:
            logger.exception('Lesson generation failed for student %s',student_id)


async def run():
    while True:
        try:
            await generate_all()
        except Exception:
            logger.exception('Lesson generation unavailable; retrying in one hour')
        await asyncio.sleep(3600)
