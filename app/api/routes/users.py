from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.database.models import UserRole
from app.services.user_service import UserService


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


class UserCreate(BaseModel):
    telegram_id: int
    role: UserRole
    name: str


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    role: UserRole
    name: str
    teacher_id: int | None = None
    student_id: int | None = None


@router.post("/", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        user = await UserService.register_user(
            session=session,
            telegram_id=data.telegram_id,
            role=data.role,
            name=data.name,
        )

        return user

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_db),
):
    user = await UserService.get_by_id(
        session,
        user_id,
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return user

@router.get("/", response_model=list[UserResponse])
async def get_users(session: AsyncSession = Depends(get_db)):
    users = await UserService.get_all_with_roles(session)

    return [
        UserResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            role=user.role,
            name=user.name,
            teacher_id=teacher_id if user.role == UserRole.TEACHER else None,
            student_id=student_id if user.role == UserRole.STUDENT else None,
        )
        for user, teacher_id, student_id in users
    ]