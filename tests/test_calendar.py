import os
import unittest
from datetime import date,datetime,time,timedelta,timezone
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock,MagicMock,patch
for k,v in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test','TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(k,v)
from sqlalchemy.dialects import postgresql
from app.services.recurrence import weekly_slots,local_instant,aware_utc
from app.services.calendar_service import CalendarService
from app.database.models import LessonStatus,UserRole

UTC=timezone.utc
NOW=datetime(2026,9,28,8,tzinfo=UTC)
def rule(**kw):
    values=dict(id=1,student_id=2,teacher_id=3,active=True,day_of_week=0,start_time=time(18),duration_minutes=60,timezone='Europe/Kyiv')
    values.update(kw)
    return Obj(**values)
def lesson(**kw):
    values=dict(id=5,student_id=2,teacher_id=3,schedule_id=1,status=LessonStatus.SCHEDULED,
                scheduled_at=NOW+timedelta(hours=7),occurrence_week=date(2026,9,28),
                is_exception=False,duration_minutes=60,timezone='Europe/Kyiv')
    values.update(kw)
    return Obj(**values)
def result(value=None,rows=None):
    obj=MagicMock()
    obj.scalar_one_or_none.return_value=value
    obj.scalar_one.return_value=value
    obj.scalars.return_value.all.return_value=rows or []
    return obj

class RecurrenceTests(unittest.TestCase):
    def test_four_weeks_and_half_open_horizon(self):
        slots=list(weekly_slots(rule(),NOW))
        self.assertEqual(len(slots),4)
        self.assertEqual(slots[0],(date(2026,9,28),datetime(2026,9,28,15,tzinfo=UTC)))
        self.assertTrue(all(NOW<=t<NOW+timedelta(days=28) for _,t in slots))
    def test_passed_lesson_not_generated(self):
        slots=list(weekly_slots(rule(),datetime(2026,9,28,20,tzinfo=UTC)))
        self.assertEqual(slots[0][0],date(2026,10,5))
    def test_utc_offset_changes_but_local_hour_stays(self):
        slots=list(weekly_slots(rule(),datetime(2026,10,5,tzinfo=UTC)))
        self.assertEqual([v.hour for _,v in slots],[15,15,15,16])
    def test_nonexistent_spring_time_is_skipped(self):
        self.assertIsNone(local_instant(date(2026,3,29),time(3,30),'Europe/Kyiv'))
        with self.assertRaises(ValueError):
            local_instant(date(2026,3,29),time(3,30),'Europe/Kyiv',strict=True)
    def test_autumn_fold_deterministic_but_manual_input_rejected(self):
        self.assertEqual(local_instant(date(2026,10,25),time(3,30),'Europe/Kyiv'),datetime(2026,10,25,0,30,tzinfo=UTC))
        with self.assertRaises(ValueError):
            local_instant(date(2026,10,25),time(3,30),'Europe/Kyiv',strict=True)
    def test_naive_datetimes_rejected(self):
        with self.assertRaises(ValueError):
            aware_utc(datetime(2026,1,1))
    def test_year_boundary(self):
        slots=list(weekly_slots(rule(day_of_week=6),datetime(2026,12,28,tzinfo=UTC)))
        self.assertEqual(slots[0][0],date(2026,12,28))
        self.assertEqual(slots[0][1].year,2027)

class GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_insert_uses_stable_slot_and_conflict_protection(self):
        session=AsyncMock()
        session.get.return_value=Obj(teacher_id=3)
        session.execute.return_value=result(value=5)
        count=await CalendarService.generate_locked(session,rule(),NOW)
        self.assertEqual(count,4)
        statement=session.execute.call_args.args[0]
        sql=str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn('ON CONFLICT ON CONSTRAINT uq_lesson_schedule_week DO NOTHING',sql)
        self.assertIn('occurrence_week',sql)
        self.assertNotIn('DO UPDATE',sql)
    async def test_duplicate_slots_are_not_counted_or_updated(self):
        session=AsyncMock()
        session.get.return_value=Obj(teacher_id=3)
        session.execute.return_value=result()
        self.assertEqual(await CalendarService.generate_locked(session,rule(),NOW),0)
    async def test_inactive_and_reassigned_student_skip_generation(self):
        session=AsyncMock()
        self.assertEqual(await CalendarService.generate_locked(session,rule(active=False),NOW),0)
        session.get.return_value=Obj(teacher_id=99)
        self.assertEqual(await CalendarService.generate_locked(session,rule(),NOW),0)
        session.execute.assert_not_awaited()

class LessonMutationTests(unittest.IsolatedAsyncioTestCase):
    async def test_reschedule_retains_slot_and_sets_exception(self):
        item=lesson()
        with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(item,True))),patch('app.services.calendar_service.utcnow',return_value=NOW):
            session=AsyncMock()
            await CalendarService.change_lesson(session,100,5,scheduled_at=NOW+timedelta(days=9))
            self.assertEqual(item.occurrence_week,date(2026,9,28))
            self.assertTrue(item.is_exception)
            session.commit.assert_awaited_once()
    async def test_cancel_retains_slot(self):
        item=lesson()
        with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(item,True))),patch('app.services.calendar_service.utcnow',return_value=NOW):
            await CalendarService.change_lesson(AsyncMock(),100,5,cancel=True)
            self.assertEqual(item.status,LessonStatus.CANCELLED)
            self.assertTrue(item.is_exception)
            self.assertEqual(item.occurrence_week,date(2026,9,28))
    async def test_past_completed_cancelled_lessons_rejected(self):
        for item in [lesson(scheduled_at=NOW),lesson(status=LessonStatus.COMPLETED),lesson(status=LessonStatus.CANCELLED)]:
            with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(item,True))),patch('app.services.calendar_service.utcnow',return_value=NOW):
                with self.assertRaises(ValueError):
                    await CalendarService.change_lesson(AsyncMock(),100,5,cancel=True)
    async def test_past_new_date_rejected(self):
        with patch.object(CalendarService,'lesson_access',AsyncMock(return_value=(lesson(),True))),patch('app.services.calendar_service.utcnow',return_value=NOW):
            with self.assertRaises(ValueError):
                await CalendarService.change_lesson(AsyncMock(),100,5,scheduled_at=NOW-timedelta(days=1))
    async def test_student_cannot_write_or_access_other_student(self):
        session=AsyncMock()
        session.execute.side_effect=[result(Obj(id=10,role=UserRole.STUDENT)),result(Obj(id=2))]
        with self.assertRaises(ValueError):
            await CalendarService.student_access(session,100,99)
        session.execute.side_effect=[result(Obj(id=10,role=UserRole.STUDENT))]
        with self.assertRaises(ValueError):
            await CalendarService.student_access(session,100,2,write=True)
    async def test_student_can_read_own_lessons(self):
        session=AsyncMock()
        session.execute.side_effect=[result(Obj(id=10,role=UserRole.STUDENT)),result(Obj(id=2))]
        student,teacher=await CalendarService.student_access(session,100)
        self.assertEqual(student.id,2)
        self.assertFalse(teacher)

class RuleUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def update(self,apply,**kwargs):
        self.item=lesson()
        self.rule=rule()
        self.session=AsyncMock()
        self.session.execute.side_effect=[result(self.rule),result(rows=[self.item]),result()]
        with patch.object(CalendarService,'generate_locked',AsyncMock()),patch('app.services.calendar_service.utcnow',return_value=NOW):
            return await CalendarService.update_rule(self.session,self.rule,day_of_week=1,start_time=time(19),
                duration_minutes=90,timezone='Europe/Kyiv',apply_future=apply,**kwargs)
    async def test_keep_mode_preserves_existing_lesson(self):
        await self.update(False)
        self.assertEqual(self.item.scheduled_at,NOW+timedelta(hours=7))
        self.assertEqual(self.item.duration_minutes,60)
        self.assertEqual(self.rule.start_time,time(19))
    async def test_apply_mode_updates_date_duration_and_zone(self):
        await self.update(True)
        self.assertEqual(self.item.scheduled_at,datetime(2026,9,29,16,tzinfo=UTC))
        self.assertEqual(self.item.duration_minutes,90)
        sql=str(self.session.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
        self.assertIn('is_exception IS false',sql)
        self.assertIn('FOR UPDATE',sql)
    async def test_stale_rule_rejected_before_any_commit(self):
        with self.assertRaises(ValueError):
            await self.update(False,expected={})
        self.session.commit.assert_not_awaited()
