"""Weekly boundaries, publication decisions and prompt retry without external services."""
import os
import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, MagicMock, patch
for k,v in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test','TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(k,v)
from sqlalchemy.dialects import postgresql
from app.database.models import Lesson, LessonStatus, WeeklySchedule
from app.services import week_service as service
from app.services.recurrence import weekly_slots, week_bounds
from app.workers import week_renewal as worker

UTC = timezone.utc
NOW = datetime(2026,10,4,17,tzinfo=UTC)  # Sunday 20:00 Kyiv
TARGET = date(2026,10,5)


def lesson(**kwargs):
    data = dict(id=1,student_id=2,schedule_id=1,status=LessonStatus.COMPLETED,
                scheduled_at=datetime(2026,9,30,15,tzinfo=UTC),duration_minutes=60)
    data.update(kwargs)
    return Obj(**data)


class BoundaryTests(unittest.TestCase):
    def test_sunday_exact_time_and_restart_catchup(self):
        self.assertEqual(service.renewal_target(NOW-timedelta(seconds=1)),date(2026,9,28))
        self.assertEqual(service.renewal_target(NOW),TARGET)
        self.assertEqual(service.renewal_target(NOW+timedelta(days=1)),TARGET)

    def test_calendar_week_spans_dst_in_local_time(self):
        start,end=week_bounds(date(2026,10,19))
        self.assertEqual(end-start,timedelta(hours=169))
        start,end=week_bounds(date(2026,3,23))
        self.assertEqual(end-start,timedelta(hours=167))

    def test_tuesday_creation_does_not_roll_passed_day_forward(self):
        now=datetime(2026,9,29,8,tzinfo=UTC)
        rule=Obj(week_start=date(2026,9,28),day_of_week=0,start_time=time(18),timezone='Europe/Kyiv')
        self.assertEqual(list(weekly_slots(rule,now)),[])
        rule.day_of_week=6
        self.assertEqual(len(list(weekly_slots(rule,now))),1)

    def test_moved_lesson_uses_actual_weekday_time(self):
        item=lesson(scheduled_at=datetime(2026,10,2,16,30,tzinfo=UTC))
        day,clock,instant=service.copied_slot(item,TARGET,NOW)
        self.assertEqual((day,clock,instant),(4,time(19,30),datetime(2026,10,9,16,30,tzinfo=UTC)))

    def test_late_answer_skips_past_slots(self):
        self.assertIsNone(service.copied_slot(lesson(),TARGET,datetime(2026,10,9,tzinfo=UTC)))

    def test_stale_and_non_monday_targets_rejected(self):
        for value in [date(2026,9,21),date(2026,10,6),date(2026,10,12)]:
            with self.assertRaises(ValueError):
                service.validate_target(value,NOW)

    def test_ambiguous_dst_copy_requires_manual_choice(self):
        item=lesson(scheduled_at=datetime(2026,10,18,0,30,tzinfo=UTC))
        with self.assertRaises(ValueError):
            service.copied_slot(item,date(2026,10,19),NOW)


class PublicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session=AsyncMock()
        self.session.add=MagicMock()
        self.row=Obj(decision='pending')
        self.patches=[patch.object(service,'decision_row',AsyncMock(return_value=self.row)),
                      patch.object(service,'week_lessons',AsyncMock(side_effect=[[],[]]))]
        for p in self.patches:
            p.start();self.addCleanup(p.stop)

    async def test_repeat_copies_regular_only_and_deduplicates(self):
        service.week_lessons.side_effect=[[
            lesson(),lesson(id=2,schedule_id=None),lesson(id=3,status=LessonStatus.CANCELLED),
            lesson(id=4),lesson(id=5,student_id=3)],[]]
        count,state=await service.decide(self.session,7,TARGET,repeat=True,now=NOW)
        self.assertEqual((count,state),(2,'repeated'))
        items=[call.args[0] for call in self.session.add.call_args_list]
        self.assertEqual(len([x for x in items if isinstance(x,Lesson)]),2)
        self.assertTrue(all(x.week_start == TARGET for x in items if isinstance(x,WeeklySchedule)))
        self.session.commit.assert_awaited_once()

    async def test_existing_target_not_duplicated(self):
        service.week_lessons.side_effect=[[lesson()],[lesson(scheduled_at=datetime(2026,10,7,15,tzinfo=UTC))]]
        self.assertEqual(await service.decide(self.session,7,TARGET,repeat=True,now=NOW),(0,'repeated'))
        self.session.add.assert_not_called()

    async def test_double_click_does_not_publish_again(self):
        self.row.decision='repeated'
        self.assertEqual(await service.decide(self.session,7,TARGET,repeat=True,now=NOW),(0,'repeated'))
        service.week_lessons.assert_not_awaited()
        self.session.add.assert_not_called()

    async def test_new_schedule_does_not_generate_or_delete_lessons(self):
        self.assertEqual(await service.decide(self.session,7,TARGET,repeat=False,now=NOW),(0,'new'))
        self.session.add.assert_not_called()
        service.week_lessons.assert_not_awaited()

    async def test_query_filters_deleted_foreign_and_outside_week(self):
        # Inspect real service SQL, rather than the patched helper.
        self.patches[1].stop()
        result=MagicMock();result.scalars.return_value.all.return_value=[]
        self.session.execute.return_value=result
        await service.week_lessons(self.session,7,TARGET,2)
        statement=self.session.execute.call_args.args[0]
        sql=str(statement.compile(dialect=postgresql.dialect()))
        for part in ['students.teacher_id =','lessons.teacher_id =','lessons.is_deleted IS false',
                     'lessons.scheduled_at >=','lessons.scheduled_at <','lessons.student_id =']:
            self.assertIn(part,sql)


class PromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_notice_and_decided_weeks_not_resent(self):
        for row in [Obj(decision='pending',message_id=99),Obj(decision='new',message_id=None)]:
            ctx=AsyncMock();session=ctx.__aenter__.return_value
            result=MagicMock();result.all.return_value=[(7,123)]
            session.execute.return_value=result
            bot=Obj(send_message=AsyncMock())
            with patch.object(worker,'AsyncSessionLocal',return_value=ctx),patch.object(worker,'week_lessons',AsyncMock(return_value=[lesson()])),patch.object(worker,'decision_row',AsyncMock(return_value=row)):
                await worker.tick(bot,NOW)
            bot.send_message.assert_not_awaited()

    async def test_success_saved_and_failure_retried(self):
        ctx=AsyncMock();session=ctx.__aenter__.return_value
        result=MagicMock();result.all.return_value=[(7,123)]
        session.execute.return_value=result
        row=Obj(decision='pending',message_id=None)
        bot=Obj(send_message=AsyncMock(side_effect=[TimeoutError(),Obj(message_id=77)]))
        with patch.object(worker,'AsyncSessionLocal',return_value=ctx),patch.object(worker,'week_lessons',AsyncMock(return_value=[lesson()])),patch.object(worker,'decision_row',AsyncMock(return_value=row)):
            await worker.tick(bot,NOW)
            self.assertIsNone(row.message_id)
            await worker.tick(bot,NOW)
        self.assertEqual(row.message_id,77)
        session.commit.assert_awaited_once()

class CreationTests(unittest.IsolatedAsyncioTestCase):
    async def test_past_and_distant_weeks_rejected_before_write(self):
        from app.database.repository.weekly_schedule_repository import WeeklyScheduleRepository
        session=AsyncMock();session.add=MagicMock()
        now=datetime(2026,9,29,8,tzinfo=UTC)
        with patch('app.services.calendar_service.utcnow',return_value=now):
            for week,day in [(date(2026,9,28),0),(date(2026,10,12),1),(date(2026,9,29),1)]:
                with self.assertRaises(ValueError):
                    await WeeklyScheduleRepository.create(session,7,2,day,time(18),60,'Europe/Kyiv',week_start=week)
        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    async def test_same_student_and_time_rejected_before_new_schedule(self):
        from app.database.repository.weekly_schedule_repository import WeeklyScheduleRepository
        session=AsyncMock();session.add=MagicMock()
        result=MagicMock();result.scalar_one_or_none.return_value=99
        session.execute.return_value=result
        with patch('app.services.calendar_service.utcnow',return_value=NOW):
            with self.assertRaises(ValueError):
                await WeeklyScheduleRepository.create(session,7,2,2,time(18),60,'Europe/Kyiv',week_start=TARGET)
        session.add.assert_not_called()

    async def test_saved_entry_marks_week_as_manually_planned(self):
        from app.database.repository.weekly_schedule_repository import WeeklyScheduleRepository
        session=AsyncMock();session.add=MagicMock()
        result=MagicMock();result.scalar_one_or_none.return_value=None
        session.execute.return_value=result
        row=Obj(decision='pending')
        with patch('app.services.calendar_service.utcnow',return_value=NOW),patch('app.services.calendar_service.CalendarService.generate_locked',AsyncMock(return_value=1)) as generate,patch.object(service,'decision_row',AsyncMock(return_value=row)):
            saved=await WeeklyScheduleRepository.create(session,7,2,2,time(18),60,'Europe/Kyiv',week_start=TARGET)
        self.assertEqual(saved.week_start,TARGET)
        self.assertEqual(row.decision,'new')
        generate.assert_awaited_once()
        session.commit.assert_awaited_once()
