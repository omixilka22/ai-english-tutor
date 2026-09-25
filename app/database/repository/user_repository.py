from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, UserRole, Teacher, Student


class UserRepository:

    @staticmethod
    async def get_by_telegram_id(
        session: AsyncSession,
        telegram_id: int,
    ) -> User | None:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        user_id: int,
    ) -> User | None:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        telegram_id: int,
        role: UserRole,
        name: str,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            role=role,
            name=name,
        )

        session.add(user)
        await session.flush()
        await session.refresh(user)

        return user

    @staticmethod
    async def update_role(
        session: AsyncSession,
        user: User,
        role: UserRole,
    ) -> User:
        user.role = role

        await session.commit()
        await session.refresh(user)

        return user

    @staticmethod
    async def get_all(
            session: AsyncSession,
    ) -> list[User]:
        result = await session.execute(
            select(User).order_by(User.id)
        )

        return list(result.scalars().all())

    @staticmethod
    async def get_all_with_roles(
            session: AsyncSession,
    ):
        result = await session.execute(
            select(User, Teacher.id, Student.id)
            .outerjoin(Teacher, Teacher.user_id == User.id)
            .outerjoin(Student, Student.user_id == User.id)
            .order_by(User.id)
        )

        return result.all()