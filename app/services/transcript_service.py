from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Transcript
from app.database.repository.transcript_repository import (
    TranscriptRepository,
)


class TranscriptService:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        transcript_id: int,
    ) -> Transcript | None:
        return await TranscriptRepository.get_by_id(
            session,
            transcript_id,
        )

    @staticmethod
    async def get_by_lesson_id(
        session: AsyncSession,
        lesson_id: int,
    ) -> Transcript | None:
        return await TranscriptRepository.get_by_lesson_id(
            session,
            lesson_id,
        )

    @staticmethod
    async def create_transcript(
        session: AsyncSession,
        lesson_id: int,
        text: str,
        source: str,
    ) -> Transcript:
        existing_transcript = (
            await TranscriptRepository.get_by_lesson_id(
                session,
                lesson_id,
            )
        )

        if existing_transcript is not None:
            raise ValueError("Transcript already exists")

        if not text.strip():
            raise ValueError("Transcript text cannot be empty")

        if not source.strip():
            raise ValueError("Transcript source cannot be empty")

        return await TranscriptRepository.create(
            session,
            lesson_id,
            text,
            source,
        )