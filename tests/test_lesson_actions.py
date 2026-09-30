import unittest
from datetime import date
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace as Obj
from sqlalchemy.dialects import postgresql
from test_calendar import lesson, result, NOW
from app.services.calendar_service import CalendarService
from app.database.models import LessonStatus
from app.database.models import Lesson
from app.database.repository.lesson_repository import LessonRepository

class LessonActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_restore_preserves_date_duration_and_slot(self):
        item=lesson(status=LessonStatus.CANCELLED,is_deleted=False,is_exception=True)
        before=(item.scheduled_at,item.occurrence_week,item.duration_minutes,item.timezone)
        with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(item,True))) as access,patch('app.services.calendar_service.utcnow',return_value=NOW):
            session=AsyncMock()
            await CalendarService.restore_lesson(session,100,5)
            self.assertEqual(item.status,LessonStatus.SCHEDULED)
            self.assertEqual(before,(item.scheduled_at,item.occurrence_week,item.duration_minutes,item.timezone))
            self.assertTrue(item.is_exception)
            access.assert_awaited_once_with(session,100,5,write=True)

    async def test_restore_past_or_non_cancelled_rejected(self):
        for item in [lesson(status=LessonStatus.CANCELLED,scheduled_at=NOW),lesson(),lesson(status=LessonStatus.COMPLETED)]:
            with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(item,True))),patch('app.services.calendar_service.utcnow',return_value=NOW):
                session=AsyncMock()
                with self.assertRaises(ValueError):
                    await CalendarService.restore_lesson(session,100,5)
                session.commit.assert_not_awaited()

    async def test_delete_keeps_recurrence_identity_and_record(self):
        item=lesson(is_deleted=False)
        with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(item,True))) as access:
            session=AsyncMock()
            await CalendarService.delete_lesson(session,100,5)
            self.assertTrue(item.is_deleted)
            self.assertEqual(item.occurrence_week,date(2026,9,28))
            self.assertTrue(item.is_exception)
            session.delete.assert_not_awaited()
            access.assert_awaited_once_with(session,100,5,write=True)

    async def test_deleted_lesson_cannot_be_opened_or_restored(self):
        session=AsyncMock()
        session.get.return_value=lesson(is_deleted=True)
        with self.assertRaises(ValueError):
            await CalendarService.restore_lesson(session,100,5)
        session.commit.assert_not_awaited()

    async def test_authorization_failure_prevents_both_actions(self):
        for operation in [CalendarService.restore_lesson,CalendarService.delete_lesson]:
            session=AsyncMock()
            with patch.object(CalendarService,'lesson_access',AsyncMock(side_effect=ValueError('Access denied'))):
                with self.assertRaises(ValueError):
                    await operation(session,999,5)
            session.commit.assert_not_awaited()

    async def test_api_repository_filters_deleted_rows(self):
        for operation in [LessonRepository.get_by_id,LessonRepository.get_by_teacher_id,LessonRepository.get_by_student_id]:
            session=AsyncMock()
            session.execute.return_value=result()
            await operation(session,5)
            sql=str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
            self.assertIn('lessons.is_deleted IS false',sql)

    async def test_calendar_list_filters_deleted_rows(self):
        session=AsyncMock()
        session.execute.return_value=result(rows=[])
        with patch.object(CalendarService,'student_access',AsyncMock(return_value=(Obj(id=2),False))),patch.object(CalendarService,'generate_for_student',AsyncMock()):
            await CalendarService.upcoming(session,100)
        sql=str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
        self.assertIn('lessons.is_deleted IS false',sql)
