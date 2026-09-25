from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Transcript


class TranscriptRepository:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        transcript_id: int,
    ) -> Transcript | None:
        result = await session.execute(
            select(Transcript).where(
                Transcript.id == transcript_id
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_lesson_id(
        session: AsyncSession,
        lesson_id: int,
    ) -> Transcript | None:
        result = await session.execute(
            select(Transcript).where(
                Transcript.lesson_id == lesson_id
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        lesson_id: int,
        text: str,
        source: str,
    ) -> Transcript:
        transcript = Transcript(
            lesson_id=lesson_id,
            text=text,
            source=source,
        )

        session.add(transcript)
        await session.commit()
        await session.refresh(transcript)

        return transcript