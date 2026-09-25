from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, UserRole
from app.database.repository.user_repository import UserRepository
from app.services.student_service  import StudentService

class UserService:

    @staticmethod
    async def get_by_telegram_id(
        session: AsyncSession,
        telegram_id: int,
    ) -> User | None:
        return await UserRepository.get_by_telegram_id(
            session,
            telegram_id,
        )

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        user_id: int,
    ) -> User | None:
        return await UserRepository.get_by_id(
            session,
            user_id,
        )

    @staticmethod
    async def register_user(
        session: AsyncSession,
        telegram_id: int,
        role: UserRole,
        name: str,
    ) -> User:
        existing_user = await UserRepository.get_by_telegram_id(
            session,
            telegram_id,
        )

        if existing_user is not None:
            raise ValueError("User already exists")

        return await UserRepository.create(
            session,
            telegram_id,
            role,
            name,
        )

    @staticmethod
    async def update_role(
        session: AsyncSession,
        user: User,
        role: UserRole,
    ) -> User:
        return await UserRepository.update_role(
            session,
            user,
            role,
        )

    @staticmethod
    async def get_all(
            session: AsyncSession,
    ) -> list[User]:
        return await UserRepository.get_all(session)

    @staticmethod
    async def get_all_with_roles(session: AsyncSession):
        return await UserRepository.get_all_with_roles(session)