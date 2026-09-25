from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.database.models import AnalysisStatus
from app.services.analysis_service import AnalysisService
from app.services.lesson_service import LessonService


router = APIRouter(
    prefix="/analysis",
    tags=["Analysis"],
)


class AnalysisCreate(BaseModel):
    lesson_id: int
    content: dict


class AnalysisResponse(BaseModel):
    id: int
    lesson_id: int
    status: AnalysisStatus
    content: dict


@router.post("/", response_model=AnalysisResponse)
async def create_analysis(
    data: AnalysisCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        lesson = await LessonService.get_by_id(
            session,
            data.lesson_id,
        )

        if lesson is None:
            raise HTTPException(
                status_code=404,
                detail="Lesson not found",
            )

        analysis = await AnalysisService.create_analysis(
            session=session,
            lesson_id=data.lesson_id,
            content=data.content,
        )

        return analysis

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/lesson/{lesson_id}", response_model=AnalysisResponse)
async def get_analysis_by_lesson(
    lesson_id: int,
    session: AsyncSession = Depends(get_db),
):
    lesson = await LessonService.get_by_id(
        session,
        lesson_id,
    )

    if lesson is None:
        raise HTTPException(
            status_code=404,
            detail="Lesson not found",
        )

    analysis = await AnalysisService.get_by_lesson_id(
        session,
        lesson_id,
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found",
        )

    return analysis


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: int,
    session: AsyncSession = Depends(get_db),
):
    analysis = await AnalysisService.get_by_id(
        session,
        analysis_id,
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found",
        )

    return analysis