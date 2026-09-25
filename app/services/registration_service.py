from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository.user_repository import UserRepository
from app.database.repository.student_repository import StudentRepository
from app.database.models import UserRole, Teacher
from app.database.repository.teacher_repository import TeacherRepository


class RegistrationService:

    @staticmethod
    async def register_student(
        session: AsyncSession,
        telegram_id: int,
        name: str,
    ):
        existing_user = await UserRepository.get_by_telegram_id(
            session,
            telegram_id,
        )

        if existing_user is not None:
            raise ValueError("User already exists")

        try:
            user = await UserRepository.create(
                session=session,
                telegram_id=telegram_id,
                role=UserRole.STUDENT,
                name=name,
            )

            await StudentRepository.create(
                session=session,
                user_id=user.id,
            )

            await session.commit()
            await session.refresh(user)

            return user

        except Exception:
            await session.rollback()
            raise

    @staticmethod
    async def register_teacher(
            session: AsyncSession,
            telegram_id: int,
            name: str,
    ):
        existing_user = await UserRepository.get_by_telegram_id(
            session,
            telegram_id,
        )

        if existing_user is not None:
            raise ValueError("User already exists")

        try:
            user = await UserRepository.create(
                session=session,
                telegram_id=telegram_id,
                role=UserRole.TEACHER,
                name=name,
            )

            teacher = Teacher(
                user_id=user.id,
            )

            session.add(teacher)

            await session.commit()
            await session.refresh(user)

            return user

        except Exception:
            await session.rollback()
            raise

    @staticmethod
    async def change_role(
        session: AsyncSession,
        telegram_id: int,
        new_role: UserRole,
    ):
        user = await UserRepository.get_by_telegram_id(
            session,
            telegram_id,
        )

        if user is None:
            raise ValueError("User not found")

        if user.role == new_role:
            raise ValueError("You already have this role")

        try:
            if new_role == UserRole.TEACHER:
                teacher = await TeacherRepository.get_by_user_id(
                    session,
                    user.id,
                )

                if teacher is None:
                    teacher = Teacher(
                        user_id=user.id,
                    )
                    session.add(teacher)

            elif new_role == UserRole.STUDENT:
                student = await StudentRepository.get_by_user_id(
                    session,
                    user.id,
                )

                if student is None:
                    await StudentRepository.create(
                        session=session,
                        user_id=user.id,
                    )

            user.role = new_role

            await session.commit()
            await session.refresh(user)

            return user

        except Exception:
            await session.rollback()
            raise