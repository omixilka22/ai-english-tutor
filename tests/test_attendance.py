import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from test_materials import NOW, lesson, analysis, result, CONTENT, Obj
from app.services import material_service as service, gemini_analysis
from app.workers import materials as worker
from app.database.models import LessonStatus
from app.bot.handlers.lessons import attendance_label

class AttendanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lesson=lesson(scheduled_at=NOW-timedelta(hours=2),conducted_at=None)
        self.session=AsyncMock();self.session.add=MagicMock()
        self.analysis=None
        for p in [patch.object(service.CalendarService,'lesson_access',AsyncMock(return_value=(self.lesson,True))),
                  patch.object(service,'analysis_for',AsyncMock(side_effect=lambda *a:self.analysis)),
                  patch.object(service,'utcnow',return_value=NOW)]:
            p.start();self.addCleanup(p.stop)
    async def test_explicit_confirmation_and_duplicate(self):
        await service.confirm_attendance(self.session,10,5)
        self.assertEqual(self.lesson.conducted_at,NOW)
        self.assertEqual(self.lesson.conducted_by,self.lesson.teacher_id)
        self.assertEqual(self.lesson.status,LessonStatus.COMPLETED)
        await service.confirm_attendance(self.session,10,5)
        self.session.commit.assert_awaited_once()
    async def test_future_cancelled_and_foreign_lesson_rejected(self):
        self.lesson.scheduled_at=NOW
        with self.assertRaises(ValueError):await service.confirm_attendance(self.session,10,5)
        self.lesson.scheduled_at=NOW-timedelta(hours=2);self.lesson.status=LessonStatus.CANCELLED
        with self.assertRaises(ValueError):await service.confirm_attendance(self.session,10,5)
        service.CalendarService.lesson_access.side_effect=ValueError('Denied')
        with self.assertRaises(ValueError):await service.confirm_attendance(self.session,10,5)
        self.session.commit.assert_not_awaited()
    async def test_forgotten_cancellation_stops_pending_materials(self):
        self.analysis=analysis(workflow_state='queued')
        await service.confirm_attendance(self.session,10,5,conducted=False)
        self.assertEqual(self.lesson.status,LessonStatus.CANCELLED)
        self.assertIsNone(self.lesson.conducted_at)
        self.assertTrue(self.lesson.is_exception)
        self.assertEqual(self.analysis.workflow_state,'blocked')
    async def test_cannot_cancel_after_approval_or_confirmed_attendance(self):
        self.analysis=analysis(workflow_state='sent')
        with self.assertRaises(ValueError):await service.confirm_attendance(self.session,10,5,conducted=False)
        self.analysis=None;self.lesson.conducted_at=NOW
        with self.assertRaises(ValueError):await service.confirm_attendance(self.session,10,5,conducted=False)
    async def test_past_and_legacy_completed_do_not_unlock_upload(self):
        self.lesson.status=LessonStatus.COMPLETED
        with self.assertRaises(ValueError):await service.upload(self.session,10,5,'Hello')
        self.session.add.assert_not_called()
        self.assertNotEqual(attendance_label(self.lesson),'Проведено')
    async def test_no_approval_or_retry_without_attendance(self):
        self.analysis=analysis()
        with self.assertRaises(ValueError):await service.approve(self.session,10,5,2)
        self.analysis.workflow_state='failed'
        with self.assertRaises(ValueError):await service.retry(self.session,10,5,2)
        self.session.commit.assert_not_awaited()

class WorkerGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfirmed_job_waits_without_ai_or_send(self):
        session=AsyncMock();session.execute.return_value=result(lesson(conducted_at=None))
        context=AsyncMock();context.__aenter__.return_value=session
        with patch.object(worker,'AsyncSessionLocal',return_value=context),patch.object(gemini_analysis,'analyze',AsyncMock()) as ai:
            await worker.process_one(AsyncMock(),5)
            ai.assert_not_awaited();session.commit.assert_not_awaited()
    async def test_503_retries_twice_then_fails_without_changing_attendance(self):
        item=lesson(status=LessonStatus.COMPLETED);job=analysis(workflow_state='queued')
        session=AsyncMock();session.execute.side_effect=lambda stmt:result(item if 'FROM lessons' in str(stmt) else job if 'FROM lesson_analyses' in str(stmt) else Obj(text='hello'))
        context=AsyncMock();context.__aenter__.return_value=session
        with patch.object(worker,'AsyncSessionLocal',return_value=context),patch.object(worker,'utcnow',return_value=NOW),patch.object(worker,'participants',AsyncMock(return_value=(Obj(telegram_id=1),Obj(telegram_id=2)))),patch.object(gemini_analysis,'analyze',AsyncMock(side_effect=gemini_analysis.AnalysisError('http_503'))) as ai:
            await worker.process_one(AsyncMock(),5)
            self.assertEqual(job.next_attempt_at,NOW+timedelta(seconds=30))
            await worker.process_one(AsyncMock(),5)
            self.assertEqual(ai.await_count,1)
            job.next_attempt_at=None
            await worker.process_one(AsyncMock(),5)
            self.assertEqual(job.next_attempt_at,NOW+timedelta(seconds=60))
            job.next_attempt_at=None
            await worker.process_one(AsyncMock(),5)
            self.assertEqual(job.workflow_state,'failed')
            self.assertEqual(job.last_error,'http_503')
            self.assertEqual(item.status,LessonStatus.COMPLETED)
            self.assertEqual(item.conducted_at,NOW)
