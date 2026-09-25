from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.services.lesson_service import LessonService
from app.services.transcript_service import TranscriptService


router = APIRouter(
    prefix="/transcripts",
    tags=["Transcripts"],
)


class TranscriptCreate(BaseModel):
    lesson_id: int
    text: str
    source: str


class TranscriptResponse(BaseModel):
    id: int
    lesson_id: int
    text: str
    source: str


@router.post("/", response_model=TranscriptResponse)
async def create_transcript(
    data: TranscriptCreate,
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

        transcript = await TranscriptService.create_transcript(
            session=session,
            lesson_id=data.lesson_id,
            text=data.text,
            source=data.source,
        )

        return transcript

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/lesson/{lesson_id}", response_model=TranscriptResponse)
async def get_transcript_by_lesson(
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

    transcript = await TranscriptService.get_by_lesson_id(
        session,
        lesson_id,
    )

    if transcript is None:
        raise HTTPException(
            status_code=404,
            detail="Transcript not found",
        )

    return transcript


@router.get("/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(
    transcript_id: int,
    session: AsyncSession = Depends(get_db),
):
    transcript = await TranscriptService.get_by_id(
        session,
        transcript_id,
    )

    if transcript is None:
        raise HTTPException(
            status_code=404,
            detail="Transcript not found",
        )

    return transcript