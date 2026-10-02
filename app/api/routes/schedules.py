from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.services.schedule_service import ScheduleService

from app.services.teacher_service import TeacherService
from app.services.student_service import StudentService


router = APIRouter(
    prefix="/schedules",
    tags=["Schedules"],
)


class ScheduleCreate(BaseModel):
    week_start: date | None = None
    teacher_id: int
    student_id: int
    day_of_week: int
    start_time: time
    duration_minutes: int
    timezone: str


class ScheduleResponse(BaseModel):
    week_start: date
    id: int
    teacher_id: int
    student_id: int
    day_of_week: int
    start_time: time
    duration_minutes: int
    timezone: str
    active: bool


@router.post("/", response_model=ScheduleResponse)
async def create_schedule(
    data: ScheduleCreate,
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

        schedule = await ScheduleService.create_schedule(
            session=session,
            teacher_id=data.teacher_id,
            student_id=data.student_id,
            day_of_week=data.day_of_week,
            start_time=data.start_time,
            duration_minutes=data.duration_minutes,
            timezone=data.timezone,
            week_start=data.week_start,
        )

        return schedule

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_db),
):
    schedule = await ScheduleService.get_by_id(
        session,
        schedule_id,
    )

    if schedule is None:
        raise HTTPException(
            status_code=404,
            detail="Schedule not found",
        )

    return schedule