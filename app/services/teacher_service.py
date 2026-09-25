from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Teacher
from app.database.repository.teacher_repository import TeacherRepository
from app.database.repository.user_repository import UserRepository
from app.database.models.user import UserRole



class TeacherService:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        teacher_id: int,
    ) -> Teacher | None:
        return await TeacherRepository.get_by_id(
            session,
            teacher_id,
        )

    @staticmethod
    async def get_by_user_id(
        session: AsyncSession,
        user_id: int,
    ) -> Teacher | None:
        return await TeacherRepository.get_by_user_id(
            session,
            user_id,
        )

    @staticmethod
    async def create_teacher(session, user_id: int) -> Teacher:
        user = await UserRepository.get_by_id(session, user_id)

        if user is None:
            raise ValueError("User not found")

        if user.role != UserRole.TEACHER:
            raise ValueError("User role must be TEACHER")

        existing_teacher = await TeacherRepository.get_by_user_id(
            session,
            user_id,
        )

        if existing_teacher is not None:
            raise ValueError("Teacher already exists")

        return await TeacherRepository.create(session, user_id)

    @staticmethod
    async def get_all(session: AsyncSession) -> list[Teacher]:
        return await TeacherRepository.get_all(session)