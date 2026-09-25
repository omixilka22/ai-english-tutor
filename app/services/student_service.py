from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Student
from app.database.repository.student_repository import StudentRepository
from app.database.repository.user_repository import UserRepository
from app.database.models.user import UserRole


class StudentService:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        student_id: int,
    ) -> Student | None:
        return await StudentRepository.get_by_id(
            session,
            student_id,
        )

    @staticmethod
    async def get_by_user_id(
        session: AsyncSession,
        user_id: int,
    ) -> Student | None:
        return await StudentRepository.get_by_user_id(
            session,
            user_id,
        )

    @staticmethod
    async def get_by_teacher_id(session, teacher_id: int):
        return await StudentRepository.get_by_teacher_id(
            session,
            teacher_id,
        )

    # @staticmethod
    # async def create_student(
    #     session: AsyncSession,
    #     user_id: int,
    #     level: str | None = None,
    # ) -> Student:
    #     existing_student = await StudentRepository.get_by_user_id(
    #         session,
    #         user_id,
    #     )
    #
    #     if existing_student is not None:
    #         raise ValueError("Student already exists")
    #
    #     return await StudentRepository.create(
    #         session,
    #         user_id,
    #         level
    #     )

    @staticmethod
    async def create_student(
            session,
            user_id: int,
            level=None,
    ) -> Student:
        user = await UserRepository.get_by_id(session, user_id)

        if user is None:
            raise ValueError("User not found")

        if user.role != UserRole.STUDENT:
            raise ValueError("User role must be STUDENT")

        existing_student = await StudentRepository.get_by_user_id(
            session,
            user_id,
        )

        if existing_student is not None:
            raise ValueError("Student already exists")

        return await StudentRepository.create(
            session,
            user_id,
            level,
        )

    @staticmethod
    async def assign_teacher(
        session: AsyncSession,
        student: Student,
        teacher_id: int,
    ) -> Student:
        if student.teacher_id is not None:
            raise ValueError("Student already has a teacher")

        return await StudentRepository.assign_teacher(
            session,
            student,
            teacher_id,
        )

    @staticmethod
    async def update_level(
        session: AsyncSession,
        student: Student,
        level: str | None,
    ) -> Student:
        return await StudentRepository.update_level(
            session,
            student,
            level,
        )
