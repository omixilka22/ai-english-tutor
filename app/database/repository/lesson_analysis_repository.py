from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AnalysisStatus,
    LessonAnalysis,
)


class LessonAnalysisRepository:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        analysis_id: int,
    ) -> LessonAnalysis | None:
        result = await session.execute(
            select(LessonAnalysis).where(
                LessonAnalysis.id == analysis_id
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_lesson_id(
        session: AsyncSession,
        lesson_id: int,
    ) -> LessonAnalysis | None:
        result = await session.execute(
            select(LessonAnalysis).where(
                LessonAnalysis.lesson_id == lesson_id
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        lesson_id: int,
        content: dict,
    ) -> LessonAnalysis:
        analysis = LessonAnalysis(
            lesson_id=lesson_id,
            content=content,
        )

        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)

        return analysis

    @staticmethod
    async def update_content(
        session: AsyncSession,
        analysis: LessonAnalysis,
        content: dict,
    ) -> LessonAnalysis:
        analysis.content = content

        await session.commit()
        await session.refresh(analysis)

        return analysis

    @staticmethod
    async def update_status(
        session: AsyncSession,
        analysis: LessonAnalysis,
        status: AnalysisStatus,
    ) -> LessonAnalysis:
        analysis.status = status

        await session.commit()
        await session.refresh(analysis)

        return analysis