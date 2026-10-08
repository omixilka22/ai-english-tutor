import unittest
from unittest.mock import AsyncMock, patch
from test_notifications import Obj, NOW
from unittest.mock import MagicMock
def result(value=None, rows=None):
    r=MagicMock();r.scalar_one_or_none.return_value=value;r.scalars.return_value.all.return_value=rows or [];return r
from app.services import student_removal as service
from app.database.models import LessonStatus

class RemoveStudentTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_removal_stops_work_and_preserves_history(self):
        from datetime import timedelta
        student=Obj(teacher_id=3,meeting_url='https://meet.google.com/abc-defg-hij',meeting_teacher_id=3)
        schedule=Obj(active=True)
        future=Obj(id=10,conducted_at=None,scheduled_at=NOW+timedelta(hours=1),duration_minutes=60,is_deleted=False,status=LessonStatus.SCHEDULED)
        history=Obj(id=11,conducted_at=NOW,scheduled_at=NOW-timedelta(days=1),duration_minutes=60,is_deleted=False,status=LessonStatus.COMPLETED)
        db=AsyncMock();db.execute.side_effect=[result(rows=[schedule]),result(rows=[future,history]),result(student),result(),result()]
        with patch.object(service.CalendarService,'student_access',AsyncMock(return_value=(student,True))),patch.object(service,'utcnow',return_value=NOW):
            await service.remove_student(db,100,2)
        self.assertIsNone(student.teacher_id);self.assertIsNone(student.meeting_url)
        self.assertFalse(schedule.active);self.assertTrue(future.is_deleted)
        self.assertFalse(history.is_deleted);self.assertEqual(history.status,LessonStatus.COMPLETED)
        db.commit.assert_awaited_once()
        updates=[str(call.args[0]) for call in db.execute.call_args_list]
        self.assertTrue(any('UPDATE lesson_notifications' in sql for sql in updates))
        self.assertTrue(any('UPDATE lesson_analyses' in sql for sql in updates))

    async def test_unauthorized_never_mutates(self):
        db=AsyncMock()
        with patch.object(service.CalendarService,'student_access',AsyncMock(side_effect=ValueError('denied'))) as auth:
            with self.assertRaises(ValueError):await service.remove_student(db,100,2)
        auth.assert_awaited_once_with(db,100,2,write=True)
        db.execute.assert_not_awaited();db.commit.assert_not_awaited()

    async def test_reassigned_student_not_detached(self):
        db=AsyncMock();current=Obj(teacher_id=4)
        db.execute.side_effect=[result(rows=[]),result(rows=[]),result(current)]
        with patch.object(service.CalendarService,'student_access',AsyncMock(return_value=(Obj(teacher_id=3),True))):
            with self.assertRaises(ValueError):await service.remove_student(db,100,2)
        self.assertEqual(current.teacher_id,4);db.commit.assert_not_awaited()

    async def test_confirmation_must_match_selected_student(self):
        from app.bot.handlers import student_removal as handler
        callback=Obj(data='remove_student_confirm_2',answer=AsyncMock())
        state=AsyncMock();state.get_data.return_value={'remove_student_id':99}
        with patch.object(handler,'remove_student',AsyncMock()) as remove,patch.object(handler,'show_screen',AsyncMock()):
            await handler.confirm(callback,state)
        remove.assert_not_awaited()
