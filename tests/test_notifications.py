import os
import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock,MagicMock,patch
for k,v in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test','TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(k,v)
from aiogram.exceptions import TelegramForbiddenError,TelegramBadRequest,TelegramRetryAfter,TelegramNetworkError
from aiogram.methods import SendMessage
from sqlalchemy.dialects import postgresql
from app.database.models import LessonStatus,UserRole
from app.services import notification_service as service
from app.services.calendar_service import CalendarService
from app.workers import notifications as worker

UTC=timezone.utc
NOW=datetime(2030,1,10,8,tzinfo=UTC)
def lesson(**kw):
    d=dict(id=5,student_id=2,teacher_id=3,scheduled_at=NOW+timedelta(hours=12),duration_minutes=60,
           timezone='Europe/Kyiv',status=LessonStatus.SCHEDULED,is_deleted=False,is_exception=False,
           notification_version=1,notification_since=NOW-timedelta(days=1))
    d.update(kw);return Obj(**d)
def job(**kw):
    d=dict(id=9,lesson_id=5,student_id=2,revision=1,kind='reminder_12h',status='pending',due_at=NOW,
           next_attempt_at=NOW,expires_at=NOW+timedelta(minutes=10),attempts=0,last_error=None)
    d.update(kw);return Obj(**d)
def recipient(**kw):
    d=dict(id=2,user_id=8,teacher_id=3,reminders_enabled=True);d.update(kw);return Obj(**d)
def result(value=None):
    r=MagicMock();r.scalar_one_or_none.return_value=value;return r

class TimingTests(unittest.TestCase):
    def test_only_12h_and_1h(self):
        times=service.reminder_times(lesson(),NOW)
        self.assertEqual([(k,d) for k,d,_ in times],[('reminder_12h',NOW),('reminder_1h',NOW+timedelta(hours=11))])
    def test_late_delivery_within_ten_minutes_only(self):
        self.assertIn('reminder_12h',[k for k,_,_ in service.reminder_times(lesson(),NOW+timedelta(minutes=10))])
        self.assertNotIn('reminder_12h',[k for k,_,_ in service.reminder_times(lesson(),NOW+timedelta(minutes=10,seconds=1))])
    def test_created_less_than_12h_before_skips_first(self):
        item=lesson(scheduled_at=NOW+timedelta(hours=5),notification_since=NOW)
        self.assertEqual([k for k,_,_ in service.reminder_times(item,NOW)],['reminder_1h'])
    def test_restore_under_one_hour_has_no_late_reminders(self):
        item=lesson(scheduled_at=NOW+timedelta(minutes=30),notification_since=NOW)
        self.assertEqual(service.reminder_times(item,NOW),[])
    def test_cancelled_deleted_started_skip(self):
        for item in [lesson(status=LessonStatus.CANCELLED),lesson(is_deleted=True),lesson(scheduled_at=NOW)]:
            self.assertEqual(service.reminder_times(item,NOW),[])
    def test_revision_role_owner_and_preference_rechecked(self):
        user=Obj(role=UserRole.STUDENT)
        for item,student in [(lesson(notification_version=2),recipient()),(lesson(),recipient(reminders_enabled=False)),
                             (lesson(),recipient(teacher_id=99)),(lesson(is_deleted=True),recipient())]:
            self.assertIsNotNone(service.invalid_reason(job(),item,student,user,NOW))
        self.assertIsNotNone(service.invalid_reason(job(),lesson(),recipient(),Obj(role=UserRole.TEACHER),NOW))
    def test_change_events_ignore_reminder_toggle(self):
        self.assertIsNone(service.invalid_reason(job(kind='moved'),lesson(),recipient(reminders_enabled=False),Obj(role=UserRole.STUDENT),NOW))
    def test_cancel_then_delete_preserves_pending_cancellation(self):
        self.assertIsNone(service.invalid_reason(job(kind='cancelled'),lesson(is_deleted=True,status=LessonStatus.CANCELLED),recipient(),Obj(role=UserRole.STUDENT),NOW))
    def test_expired_notifications_rejected(self):
        self.assertEqual(service.invalid_reason(job(),lesson(),recipient(),Obj(role=UserRole.STUDENT),NOW+timedelta(minutes=11)),'expired_or_missing')
    def test_late_reminder_text_shows_actual_remaining_time(self):
        text,markup=worker.notification_content(job(),lesson(),NOW+timedelta(minutes=5))
        self.assertIn('11 год 55 хв',text)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data,'notification_lesson_5')
    def test_deleted_notice_opens_list(self):
        _,markup=worker.notification_content(job(kind='deleted'),lesson(is_deleted=True),NOW)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data,'notification_list')

class OutboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_unique_key_includes_revision_type_and_recipient(self):
        session=AsyncMock()
        await service.enqueue(session,lesson(),'reminder_12h',NOW,NOW+timedelta(minutes=10))
        stmt=session.execute.call_args.args[0]
        self.assertIn('ON CONFLICT ON CONSTRAINT uq_lesson_notification DO NOTHING',str(stmt.compile(dialect=postgresql.dialect())))
        params=stmt.compile().params
        self.assertEqual((params['revision'],params['student_id'],params['kind']),(1,2,'reminder_12h'))
    async def test_change_recorded_without_committing_callers_transaction(self):
        session=AsyncMock();item=lesson()
        await service.record_change(session,item,'moved',NOW)
        self.assertEqual(item.notification_version,2)
        self.assertEqual(item.notification_since,NOW)
        session.execute.assert_awaited_once();session.commit.assert_not_awaited()
    async def test_suppressed_change_invalidates_without_new_message(self):
        session=AsyncMock();item=lesson()
        await service.record_change(session,item,None,NOW)
        self.assertEqual(item.notification_version,2)
        session.execute.assert_not_awaited()
    async def test_cancelled_deletion_does_not_invalidate_pending_cancel(self):
        item=lesson(status=LessonStatus.CANCELLED)
        with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(item,True))),patch('app.services.calendar_service.record_change',AsyncMock()) as change:
            await CalendarService.delete_lesson(AsyncMock(),100,5)
            change.assert_not_awaited();self.assertEqual(item.notification_version,1)
    async def test_move_and_notification_share_commit(self):
        session=AsyncMock();item=lesson()
        with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(item,True))),patch('app.services.calendar_service.utcnow',return_value=NOW):
            await CalendarService.change_lesson(session,100,5,scheduled_at=NOW+timedelta(hours=20))
        self.assertEqual(item.notification_version,2)
        session.execute.assert_awaited_once();session.commit.assert_awaited_once()
    async def test_notification_insert_failure_prevents_commit(self):
        session=AsyncMock();session.execute.side_effect=RuntimeError('database failure')
        with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(lesson(),True))),patch('app.services.calendar_service.utcnow',return_value=NOW):
            with self.assertRaises(RuntimeError):
                await CalendarService.change_lesson(session,100,5,cancel=True)
        session.commit.assert_not_awaited()
    async def test_preference_requires_student(self):
        session=AsyncMock();session.execute.return_value=result(Obj(id=8,role=UserRole.TEACHER))
        with self.assertRaises(ValueError):await service.set_preference(session,100,False)
        session.commit.assert_not_awaited()
    async def test_preference_persists(self):
        student=recipient();session=AsyncMock()
        session.execute.side_effect=[result(Obj(id=8,role=UserRole.STUDENT)),result(student)]
        await service.set_preference(session,100,False)
        self.assertFalse(student.reminders_enabled);session.commit.assert_awaited_once()

class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.job=job();self.lesson=lesson();self.student=recipient()
        self.user=Obj(role=UserRole.STUDENT,telegram_id=100)
        self.session=AsyncMock()
        self.session.get.side_effect=lambda cls,key: self.job if key==9 else self.user
        self.session.execute.side_effect=lambda stmt: result(self.lesson if 'FROM lessons' in str(stmt) else self.student if 'FROM students' in str(stmt) else self.job)
        context=AsyncMock();context.__aenter__.return_value=self.session
        self.bot=Obj(send_message=AsyncMock(return_value=Obj(message_id=777)))
        for p in [patch.object(worker,'AsyncSessionLocal',return_value=context),patch.object(worker,'utcnow',return_value=NOW)]:
            p.start();self.addCleanup(p.stop)
    async def test_success_records_telegram_id_and_sent_status(self):
        await worker.deliver_one(self.bot,9)
        self.assertEqual(self.job.status,'sent');self.assertEqual(self.job.telegram_message_id,777)
        self.bot.send_message.assert_awaited_once();self.session.commit.assert_awaited_once()
        statements=[str(c.args[0].compile(dialect=postgresql.dialect())) for c in self.session.execute.call_args_list]
        self.assertIn('FOR UPDATE',statements[0]);self.assertIn('SKIP LOCKED',statements[1])
    async def test_second_delivery_does_not_send(self):
        await worker.deliver_one(self.bot,9)
        await worker.deliver_one(self.bot,9)
        self.bot.send_message.assert_awaited_once()
    async def test_stale_revision_skipped_without_send(self):
        self.lesson.notification_version=2
        await worker.deliver_one(self.bot,9)
        self.assertEqual(self.job.status,'skipped');self.bot.send_message.assert_not_awaited()
    async def test_disabled_skipped_without_send(self):
        self.student.reminders_enabled=False
        await worker.deliver_one(self.bot,9)
        self.assertEqual(self.job.status,'skipped');self.bot.send_message.assert_not_awaited()
    async def test_network_error_retries_with_backoff(self):
        self.bot.send_message.side_effect=TelegramNetworkError(method=SendMessage(chat_id=100,text='x'),message='test')
        await worker.deliver_one(self.bot,9)
        self.assertEqual(self.job.status,'pending');self.assertEqual(self.job.next_attempt_at,NOW+timedelta(seconds=30))
        self.assertEqual(self.job.attempts,1)
    async def test_telegram_rate_limit_delays_next_attempt(self):
        self.bot.send_message.side_effect=TelegramRetryAfter(method=SendMessage(chat_id=100,text='x'),message='test',retry_after=60)
        self.assertEqual(await worker.deliver_one(self.bot,9),60)
        self.assertEqual(self.job.next_attempt_at,NOW+timedelta(seconds=60))
    async def test_blocked_user_fails_without_infinite_retry(self):
        self.bot.send_message.side_effect=TelegramForbiddenError(method=SendMessage(chat_id=100,text='x'),message='blocked')
        await worker.deliver_one(self.bot,9)
        await worker.deliver_one(self.bot,9)
        self.assertEqual(self.job.status,'failed');self.bot.send_message.assert_awaited_once()
    async def test_retry_limit(self):
        self.job.attempts=4
        self.bot.send_message.side_effect=TimeoutError()
        await worker.deliver_one(self.bot,9)
        self.assertEqual(self.job.status,'failed');self.assertEqual(self.job.attempts,5)
    async def test_not_due_does_not_send(self):
        self.job.next_attempt_at=NOW+timedelta(minutes=1)
        await worker.deliver_one(self.bot,9)
        self.bot.send_message.assert_not_awaited()
