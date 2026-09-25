import asyncio
from datetime import datetime, time, timedelta

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import UserRole, LessonStatus, AnalysisStatus

from app.services.user_service import UserService
from app.services.teacher_service import TeacherService
from app.services.student_service import StudentService
from app.services.invite_service import InviteService
from app.services.schedule_service import ScheduleService
from app.services.lesson_service import LessonService
from app.services.transcript_service import TranscriptService
from app.services.analysis_service import AnalysisService


async def main():
    async with AsyncSessionLocal() as session:

        print("\n=== USER ===")

        teacher_user = await UserService.register_user(
            session,
            telegram_id=100000001,
            role=UserRole.TEACHER,
            name="Test Teacher",
        )

        student_user = await UserService.register_user(
            session,
            telegram_id=100000002,
            role=UserRole.STUDENT,
            name="Test Student",
        )

        print(
            "Teacher user:",
            teacher_user.id,
            teacher_user.name,
        )

        print(
            "Student user:",
            student_user.id,
            student_user.name,
        )

        print("\n=== TEACHER ===")

        teacher = await TeacherService.create_teacher(
            session,
            teacher_user.id,
        )

        print(
            "Teacher:",
            teacher.id,
            teacher.user_id,
        )

        print("\n=== STUDENT ===")

        student = await StudentService.create_student(
            session,
            student_user.id,
            level="B1",
        )

        print(
            "Student:",
            student.id,
            student.user_id,
            student.level,
        )

        print("\n=== INVITE ===")

        invite = await InviteService.create_invite(
            session,
            teacher.id,
            expires_in_hours=24,
        )

        print(
            "Invite:",
            invite.id,
            invite.token,
        )

        validated_invite = await InviteService.validate_invite(
            session,
            invite.token,
        )

        print(
            "Invite validated:",
            validated_invite.id,
        )

        student = await InviteService.use_invite(
            session,
            validated_invite,
            student,
        )

        print(
            "Student teacher_id:",
            student.teacher_id,
        )

        print("\n=== SCHEDULE ===")

        schedule = await ScheduleService.create_schedule(
            session,
            teacher_id=teacher.id,
            student_id=student.id,
            day_of_week=0,
            start_time=time(18, 0),
            duration_minutes=60,
            timezone="Europe/Kyiv",
        )

        print(
            "Schedule:",
            schedule.id,
            schedule.day_of_week,
            schedule.start_time,
            schedule.duration_minutes,
        )

        print("\n=== LESSON ===")

        lesson = await LessonService.create_lesson(
            session,
            teacher_id=teacher.id,
            student_id=student.id,
            scheduled_at=datetime.now(),
            schedule_id=schedule.id,
        )

        print(
            "Lesson:",
            lesson.id,
            lesson.status,
        )

        lesson = await LessonService.update_status(
            session,
            lesson,
            LessonStatus.COMPLETED,
        )

        print(
            "Lesson status:",
            lesson.status,
        )

        print("\n=== TRANSCRIPT ===")

        transcript = await TranscriptService.create_transcript(
            session,
            lesson_id=lesson.id,
            text="Hello! Today we talked about travelling.",
            source="test",
        )

        print(
            "Transcript:",
            transcript.id,
            transcript.source,
        )

        print("\n=== ANALYSIS ===")

        analysis_content = {
            "summary": "Student talked about travelling.",
            "vocabulary": [
                {
                    "word": "journey",
                    "translation": "подорож",
                    "contextual_example": "It was a long journey.",
                }
            ],
            "grammar_mistakes": [],
            "useful_expressions": [],
            "homework": [
                {
                    "task": "Practice new vocabulary",
                    "description": "Write 5 sentences.",
                }
            ],
        }

        analysis = await AnalysisService.create_analysis(
            session,
            lesson_id=lesson.id,
            content=analysis_content,
        )

        print(
            "Analysis:",
            analysis.id,
            analysis.status,
        )

        analysis = await AnalysisService.update_status(
            session,
            analysis,
            AnalysisStatus.READY_FOR_REVIEW,
        )

        print(
            "Analysis status:",
            analysis.status,
        )

        print("\n=== SERVICES TEST COMPLETED ===")


if __name__ == "__main__":
    asyncio.run(main())