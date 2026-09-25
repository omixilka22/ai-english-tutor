from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.services.teacher_service import TeacherService


router = APIRouter(
    prefix="/teachers",
    tags=["Teachers"],
)


class TeacherCreate(BaseModel):
    user_id: int


class TeacherResponse(BaseModel):
    id: int
    user_id: int


@router.post("/", response_model=TeacherResponse)
async def create_teacher(
    data: TeacherCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        teacher = await TeacherService.create_teacher(
            session=session,
            user_id=data.user_id,
        )

        return teacher

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/{teacher_id}", response_model=TeacherResponse)
async def get_teacher(
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

    return teacher

@router.get("/", response_model=list[TeacherResponse])
async def get_teachers(session: AsyncSession = Depends(get_db)):
    return await TeacherService.get_all(session)