from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.services.student_service import StudentService
from app.services.teacher_service import TeacherService


router = APIRouter(
    prefix="/students",
    tags=["Students"],
)


class StudentCreate(BaseModel):
    user_id: int
    level: str | None = None


class StudentResponse(BaseModel):
    id: int
    user_id: int
    teacher_id: int | None
    level: str | None


@router.post("/", response_model=StudentResponse)
async def create_student(
    data: StudentCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        student = await StudentService.create_student(
            session=session,
            user_id=data.user_id,
            level=data.level,
        )

        return student

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(
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

    return student

class AssignTeacherRequest(BaseModel):
    teacher_id: int


@router.post("/{student_id}/teacher", response_model=StudentResponse)
async def assign_teacher(
    student_id: int,
    data: AssignTeacherRequest,
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

    teacher = await TeacherService.get_by_id(
        session,
        data.teacher_id,
    )

    if teacher is None:
        raise HTTPException(
            status_code=404,
            detail="Teacher not found",
        )

    try:
        student = await StudentService.assign_teacher(
            session=session,
            student=student,
            teacher_id=data.teacher_id,
        )

        return student

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

@router.get("/teacher/{teacher_id}", response_model=list[StudentResponse])
async def get_students_by_teacher(
    teacher_id: int,
    session: AsyncSession = Depends(get_db),
):
    students = await StudentService.get_by_teacher_id(
        session,
        teacher_id,
    )
    return students