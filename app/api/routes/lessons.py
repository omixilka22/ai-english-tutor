from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.database.models import LessonStatus
from app.services.lesson_service import LessonService
from app.services.teacher_service import TeacherService
from app.services.student_service import StudentService
from app.services.schedule_service import ScheduleService


router = APIRouter(
    prefix="/lessons",
    tags=["Lessons"],
)


class LessonCreate(BaseModel):
    teacher_id: int
    student_id: int
    schedule_id: int | None = None
    scheduled_at: datetime


class LessonResponse(BaseModel):
    id: int
    teacher_id: int
    student_id: int
    schedule_id: int | None
    scheduled_at: datetime
    status: LessonStatus


@router.post("/", response_model=LessonResponse)
async def create_lesson(
    data: LessonCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        teacher = await TeacherService.get_by_id(
            session,
            data.teacher_id,
        )

        if teacher is None:
            raise HTTPException(
                status_code=404,
                detail="Teacher not found",
            )

        student = await StudentService.get_by_id(
            session,
            data.student_id,
        )

        if student is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found",
            )

        if data.schedule_id is not None:
            schedule = await ScheduleService.get_by_id(
                session,
                data.schedule_id,
            )

            if schedule is None:
                raise HTTPException(
                    status_code=404,
                    detail="Schedule not found",
                )

        lesson = await LessonService.create_lesson(
            session=session,
            teacher_id=data.teacher_id,
            student_id=data.student_id,
            scheduled_at=data.scheduled_at,
            schedule_id=data.schedule_id,
        )

        return lesson

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/{lesson_id}", response_model=LessonResponse)
async def get_lesson(
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

    return lesson


@router.get("/teacher/{teacher_id}", response_model=list[LessonResponse])
async def get_lessons_by_teacher(
    teacher_id: int,
    session: AsyncSession = Depends(get_db),
):
    teacher = await TeacherService.get_by_id(
        session,
        teacher_id,
    )

    if teacher is None:
        raise HTTPException(
            status_code=404,
            detail="Teacher not found",
        )

    return await LessonService.get_by_teacher_id(
        session,
        teacher_id,
    )


@router.get("/student/{student_id}", response_model=list[LessonResponse])
async def get_lessons_by_student(
    student_id: int,
    session: AsyncSession = Depends(get_db),
):
    student = await StudentService.get_by_id(
        session,
        student_id,
    )

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    return await LessonService.get_by_student_id(
        session,
        student_id,
    )