"""Isolated tests; no PostgreSQL writes or Telegram requests."""
import os
import unittest
from datetime import time
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, patch

for name, value in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test',
                    'TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(name,value)

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.exc import SQLAlchemyError
from app.bot.handlers import schedules as ui
from app.bot.states.schedule import ScheduleState
from app.database.models import UserRole
from app.services.schedule_service import ScheduleService


class ValidationTests(unittest.TestCase):
    def test_valid_times(self):
        for raw, expected in [('00:00',time(0)),('23:59',time(23,59)),(' 18:30 ',time(18,30))]:
            self.assertEqual(ui.parse_time(raw),expected)

    def test_invalid_times(self):
        for raw in [None,'','9:00','24:00','12:60','18:30:00','hello']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                ui.parse_time(raw)

    def test_invalid_schedule_fields(self):
        for day,duration,tz in [(-1,60,'UTC'),(7,60,'UTC'),(1,0,'UTC'),(1,1441,'UTC'),(1,60,'Invalid/City')]:
            with self.subTest(day=day,duration=duration,tz=tz), self.assertRaises(ValueError):
                ScheduleService.validate_schedule(day,time(18),duration,tz)

    def test_offset_time_rejected(self):
        with self.assertRaises(ValueError):
            ScheduleService.validate_schedule(1,time.fromisoformat('18:00+03:00'),60,'Europe/Kyiv')


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_foreign_student_rejected(self):
        for student in [None,Obj(teacher_id=2)]:
            with patch('app.services.schedule_service.StudentRepository.get_by_id',AsyncMock(return_value=student)), patch('app.services.schedule_service.WeeklyScheduleRepository.create',AsyncMock()) as create:
                with self.assertRaises(ValueError):
                    await ScheduleService.create_schedule(AsyncMock(),1,10,0,time(18),60,'Europe/Kyiv')
                create.assert_not_awaited()

    async def test_owned_student_saved(self):
        with patch('app.services.schedule_service.StudentRepository.get_by_id',AsyncMock(return_value=Obj(teacher_id=1))), patch('app.services.schedule_service.WeeklyScheduleRepository.create',AsyncMock(return_value='saved')) as create:
            session=AsyncMock()
            self.assertEqual(await ScheduleService.create_schedule(session,1,10,0,time(18),60,'Europe/Kyiv'),'saved')
            create.assert_awaited_once_with(session,1,10,0,time(18),60,'Europe/Kyiv',week_start=None)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage=MemoryStorage()
        self.state=FSMContext(storage=self.storage,key=StorageKey(bot_id=1,chat_id=2,user_id=2))
        self.message=Obj(text='18:30',answer=AsyncMock(),edit_reply_markup=AsyncMock())
        self.callback=Obj(data='add_schedule_10',from_user=Obj(id=2),message=self.message,answer=AsyncMock())
        self.session=AsyncMock()
        context=AsyncMock()
        context.__aenter__.return_value=self.session
        async def screen(event, state, text, reply_markup=None):
            message = getattr(event, 'message', event)
            await message.answer(text, reply_markup=reply_markup)
        for p in [patch.object(ui,'show_screen',side_effect=screen),
                  patch('app.bot.ui.show_screen',side_effect=screen),
                  patch.object(ui.UserService,'get_by_id',AsyncMock(return_value=Obj(name='Test Student'))),
                  patch.object(ui,'AsyncSessionLocal',return_value=context),
                  patch.object(ui.UserService,'get_by_telegram_id',AsyncMock(return_value=Obj(id=2,role=UserRole.TEACHER))),
                  patch.object(ui.TeacherService,'get_by_user_id',AsyncMock(return_value=Obj(id=1))),
                  patch.object(ui.StudentService,'get_by_id',AsyncMock(return_value=Obj(id=10,teacher_id=1,user_id=3))),
                  patch.object(ui.ScheduleService,'create_schedule',AsyncMock())]:
            p.start()
            self.addCleanup(p.stop)

    async def asyncTearDown(self):
        await self.storage.close()

    async def prepare(self):
        await ui.add_schedule(self.callback,self.state)
        self.assertEqual(await self.state.get_state(),ScheduleState.choosing_day.state)
        self.callback.data='schedule_day_0'
        await ui.choose_day(self.callback,self.state)
        self.assertEqual(await self.state.get_state(),ScheduleState.waiting_for_time.state)
        await ui.enter_time(self.message,self.state)
        self.assertEqual(await self.state.get_state(),ScheduleState.choosing_duration.state)
        self.callback.data='schedule_duration_60'
        await ui.choose_duration(self.callback,self.state)
        self.assertEqual(await self.state.get_state(),ScheduleState.confirming.state)
        self.callback.data='schedule_confirm'

    async def test_full_flow(self):
        await self.prepare()
        await ui.confirm_schedule(self.callback,self.state)
        ui.ScheduleService.create_schedule.assert_awaited_once_with(self.session,teacher_id=1,student_id=10,day_of_week=0,start_time=time(18,30),duration_minutes=60,timezone='Europe/Kyiv',week_start=ui.week_monday())
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(await self.state.get_data(),{})

    async def test_confirmation_filter_rejects_duplicate_after_save(self):
        await self.prepare()
        handler = next(h for h in ui.router.callback_query.handlers if h.callback is ui.confirm_schedule)
        accepted, _ = await handler.check(self.callback, raw_state=await self.state.get_state())
        self.assertTrue(accepted)
        await ui.confirm_schedule(self.callback, self.state)
        accepted, _ = await handler.check(self.callback, raw_state=await self.state.get_state())
        self.assertFalse(accepted)

    async def test_stale_confirmation_does_not_save(self):
        await ui.stale_schedule_button(self.callback)
        ui.ScheduleService.create_schedule.assert_not_awaited()

    async def test_invalid_input_keeps_state(self):
        await self.state.set_state(ScheduleState.waiting_for_time)
        await self.state.update_data(student_id=10,day_of_week=0,week_start=ui.week_monday().isoformat())
        self.message.text=None
        await ui.enter_time(self.message,self.state)
        self.assertEqual(await self.state.get_state(),ScheduleState.waiting_for_time.state)

    async def test_cancel_discards_draft(self):
        await self.prepare()
        await ui.cancel_schedule(self.callback,self.state)
        self.assertEqual(await self.state.get_data(),{})
        self.assertIsNone(await self.state.get_state())
        ui.ScheduleService.create_schedule.assert_not_awaited()

    async def test_foreign_student_at_entry(self):
        ui.StudentService.get_by_id.return_value.teacher_id=99
        await ui.add_schedule(self.callback,self.state)
        self.assertIsNone(await self.state.get_state())
        ui.ScheduleService.create_schedule.assert_not_awaited()

    async def test_ownership_rechecked_at_save(self):
        await self.prepare()
        ui.StudentService.get_by_id.return_value.teacher_id=99
        await ui.confirm_schedule(self.callback,self.state)
        ui.ScheduleService.create_schedule.assert_not_awaited()

    async def test_role_rechecked_at_save(self):
        await self.prepare()
        ui.UserService.get_by_telegram_id.return_value.role=UserRole.STUDENT
        await ui.confirm_schedule(self.callback,self.state)
        ui.ScheduleService.create_schedule.assert_not_awaited()

    async def test_database_failure_allows_retry(self):
        await self.prepare()
        ui.ScheduleService.create_schedule.side_effect=SQLAlchemyError('test failure')
        await ui.confirm_schedule(self.callback,self.state)
        self.session.rollback.assert_awaited_once()
        self.assertEqual(await self.state.get_state(),ScheduleState.confirming.state)

    async def test_view_uses_actual_week_lessons(self):
        from datetime import datetime, timezone
        from app.database.models import LessonStatus
        lesson = Obj(id=60, scheduled_at=datetime(2026,10,2,18,tzinfo=timezone.utc),
                     duration_minutes=60,status=LessonStatus.CANCELLED)
        with patch.object(ui, 'week_lessons', AsyncMock(return_value=[lesson])) as query:
            self.callback.data='student_schedule_10'
            await ui.student_schedule(self.callback,self.state)
        query.assert_awaited_once_with(self.session, 1, ui.week_monday(), 10)
        markup=self.message.answer.call_args.kwargs['reply_markup']
        self.assertTrue(any('Скасовано' in button.text for row in markup.inline_keyboard for button in row))

if __name__=='__main__':
    unittest.main()
