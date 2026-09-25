from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Student, User


class StudentRepository:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        student_id: int,
    ) -> Student | None:
        result = await session.execute(
            select(Student).where(Student.id == student_id)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_id(
        session: AsyncSession,
        user_id: int,
    ) -> Student | None:
        result = await session.execute(
            select(Student).where(Student.user_id == user_id)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_teacher_id(
            session: AsyncSession,
            teacher_id: int,
    ):
        result = await session.execute(
            select(Student, User)
            .join(User, Student.user_id == User.id)
            .where(Student.teacher_id == teacher_id)
        )

        return result.all()

    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: int,
        level: str | None = None,
    ) -> Student:
        student = Student(
            user_id=user_id,
            level=level,
        )

        session.add(student)
        await session.flush()
        await session.refresh(student)

        return student

    @staticmethod
    async def assign_teacher(
        session: AsyncSession,
        student: Student,
        teacher_id: int,
    ) -> Student:
        student.teacher_id = teacher_id

        await session.commit()
        await session.refresh(student)

        return student

    @staticmethod
    async def update_level(
        session: AsyncSession,
        student: Student,
        level: str | None,
    ) -> Student:
        student.level = level

        await session.commit()
        await session.refresh(student)

        return student