import asyncio
from datetime import datetime, time, timedelta

from app.database.database import AsyncSessionLocal

from app.database.models import (
    UserRole,
    LessonStatus,
    AnalysisStatus,
)

from app.database.repository.user_repository import UserRepository
from app.database.repository.teacher_repository import TeacherRepository
from app.database.repository.student_repository import StudentRepository
from app.database.repository.teacher_invite_repository import TeacherInviteRepository
from app.database.repository.weekly_schedule_repository import WeeklyScheduleRepository
from app.database.repository.lesson_repository import LessonRepository
from app.database.repository.transcript_repository import TranscriptRepository
from app.database.repository.lesson_analysis_repository import LessonAnalysisRepository


async def main():

    async with AsyncSessionLocal() as session:

        # USER
        teacher_user = await UserRepository.create(
            session,
            telegram_id=111111111,
            role=UserRole.TEACHER,
            name="Teacher Test",
        )

        student_user = await UserRepository.create(
            session,
            telegram_id=222222222,
            role=UserRole.STUDENT,
            name="Student Test",
        )

        print("USERS:", teacher_user.id, student_user.id)


        # TEACHER
        teacher = await TeacherRepository.create(
            session,
            user_id=teacher_user.id,
        )

        print("TEACHER:", teacher.id)


        # STUDENT
        student = await StudentRepository.create(
            session,
            user_id=student_user.id,
            level="B1",
        )

        student = await StudentRepository.assign_teacher(
            session,
            student,
            teacher.id,
        )

        print(
            "STUDENT:",
            student.id,
            student.teacher_id
        )


        # INVITE
        invite = await TeacherInviteRepository.create(
            session,
            teacher_id=teacher.id,
            token="test-token-123",
            expires_at=datetime.utcnow() + timedelta(days=7),
        )

        print("INVITE:", invite.id)


        # SCHEDULE
        schedule = await WeeklyScheduleRepository.create(
            session,
            teacher_id=teacher.id,
            student_id=student.id,
            day_of_week=1,
            start_time=time(18, 0),
            duration_minutes=60,
            timezone="Europe/Kyiv",
        )

        print("SCHEDULE:", schedule.id)


        # LESSON
        lesson = await LessonRepository.create(
            session,
            teacher_id=teacher.id,
            student_id=student.id,
            schedule_id=schedule.id,
            scheduled_at=datetime.utcnow(),
        )

        print("LESSON:", lesson.id)


        lesson = await LessonRepository.update_status(
            session,
            lesson,
            LessonStatus.COMPLETED,
        )

        print("LESSON STATUS:", lesson.status)


        # TRANSCRIPT
        transcript = await TranscriptRepository.create(
            session,
            lesson_id=lesson.id,
            text="Hello, today we practiced English grammar.",
            source="google_meet",
        )

        print("TRANSCRIPT:", transcript.id)


        # ANALYSIS
        analysis = await LessonAnalysisRepository.create(
            session,
            lesson_id=lesson.id,
            content={
                "summary": "Grammar lesson",
                "mistakes": [],
                "homework": "Practice Past Simple",
            },
        )

        analysis = await LessonAnalysisRepository.update_status(
            session,
            analysis,
            AnalysisStatus.READY_FOR_REVIEW,
        )

        print(
            "ANALYSIS:",
            analysis.id,
            analysis.status
        )


asyncio.run(main())