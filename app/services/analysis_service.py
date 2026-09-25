from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AnalysisStatus, LessonAnalysis
from app.database.repository.lesson_analysis_repository import (
    LessonAnalysisRepository,
)


class AnalysisService:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        analysis_id: int,
    ) -> LessonAnalysis | None:
        return await LessonAnalysisRepository.get_by_id(
            session,
            analysis_id,
        )

    @staticmethod
    async def get_by_lesson_id(
        session: AsyncSession,
        lesson_id: int,
    ) -> LessonAnalysis | None:
        return await LessonAnalysisRepository.get_by_lesson_id(
            session,
            lesson_id,
        )

    @staticmethod
    async def create_analysis(
            session: AsyncSession,
            lesson_id: int,
            content: dict,
    ) -> LessonAnalysis:
        existing_analysis = (
            await LessonAnalysisRepository.get_by_lesson_id(
                session,
                lesson_id,
            )
        )

        if existing_analysis is not None:
            raise ValueError("Lesson analysis already exists")

        if not content:
            raise ValueError("Lesson analysis content cannot be empty")

        return await LessonAnalysisRepository.create(
            session,
            lesson_id,
            content,
        )

    @staticmethod
    async def update_content(
        session: AsyncSession,
        analysis: LessonAnalysis,
        content: dict,
    ) -> LessonAnalysis:
        return await LessonAnalysisRepository.update_content(
            session,
            analysis,
            content,
        )

    @staticmethod
    async def update_status(
        session: AsyncSession,
        analysis: LessonAnalysis,
        status: AnalysisStatus,
    ) -> LessonAnalysis:
        return await LessonAnalysisRepository.update_status(
            session,
            analysis,
            status,
        )