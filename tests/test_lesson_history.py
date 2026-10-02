from test_materials import NOW, lesson, Obj
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock,MagicMock,patch
from app.services import calendar_service as service
from app.bot.handlers import lessons as ui
from app.database.models import LessonStatus

class LessonStatusTests(unittest.TestCase):
    def test_status_changes_at_start_and_end_not_before(self):
        item=lesson(scheduled_at=NOW,duration_minutes=60,conducted_at=None)
        for now,label in [(NOW-timedelta(seconds=1),'Заплановано'),(NOW,'Триває'),(NOW+timedelta(minutes=59),'Триває'),(NOW+timedelta(hours=1),'Очікує підтвердження викладача')]:
            with patch.object(ui,'utcnow',return_value=now):self.assertEqual(ui.attendance_label(item),label)
        item.conducted_at=NOW+timedelta(hours=1)
        self.assertEqual(ui.attendance_label(item),'Проведено')
        item.status=LessonStatus.CANCELLED
        self.assertEqual(ui.attendance_label(item),'Скасовано')
    def test_week_boundary_uses_kyiv(self):
        sunday_utc=datetime(2026,10,4,21,30,tzinfo=timezone.utc)
        self.assertEqual(service.current_week_start(sunday_utc),datetime(2026,10,4,21,tzinfo=timezone.utc))

class HistoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_list_keeps_conducted_lessons_and_filters_teacher(self):
        session=AsyncMock();res=MagicMock()
        done=lesson(teacher_id=3,status=LessonStatus.COMPLETED)
        res.scalars.return_value.all.return_value=[done,lesson(teacher_id=99)]
        session.execute.return_value=res
        with patch.object(service.CalendarService,'student_access',AsyncMock(return_value=(Obj(id=2,teacher_id=3),True))),patch.object(service.CalendarService,'generate_for_student',AsyncMock()),patch.object(service,'utcnow',return_value=NOW):
            _,_,items=await service.CalendarService.upcoming(session,100,2)
        self.assertEqual(items,[done])
        statement=session.execute.call_args.args[0]
        self.assertIn(service.current_week_start(NOW),statement.compile().params.values())
        self.assertNotIn(NOW,statement.compile().params.values())
    async def test_history_scope_and_no_generation(self):
        session=AsyncMock();res=MagicMock();res.scalars.return_value.all.return_value=[];session.execute.return_value=res
        with patch.object(service.CalendarService,'student_access',AsyncMock(return_value=(Obj(id=2,teacher_id=3),True))),patch.object(service.CalendarService,'generate_for_student',AsyncMock()) as generation:
            await service.CalendarService.history(session,100,2)
            generation.assert_not_awaited()
        query=str(session.execute.call_args.args[0])
        self.assertIn('lessons.teacher_id',query)
        self.assertIn('lessons.is_deleted IS false',query)
        self.assertIn('DESC',query)
