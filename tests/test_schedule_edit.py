import os
import unittest
from datetime import time
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock,patch
for k,v in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test','TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(k,v)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.exc import SQLAlchemyError
from app.bot.handlers import schedule_edit as edit
from app.database.models import UserRole
from app.bot.ui import clear_flow

class EditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage=MemoryStorage()
        self.state=FSMContext(self.storage,StorageKey(bot_id=1,chat_id=2,user_id=2))
        self.callback=Obj(data='edit_schedule_7',from_user=Obj(id=2),answer=AsyncMock())
        self.schedule=Obj(id=7,student_id=9,teacher_id=1,active=True,day_of_week=1,
                          start_time=time(18,30),duration_minutes=50,timezone='Europe/Warsaw')
        ctx=AsyncMock()
        self.session=ctx.__aenter__.return_value
        for p in [patch.object(edit,'AsyncSessionLocal',return_value=ctx),
                  patch.object(edit,'show_screen',AsyncMock()),
                  patch.object(edit.UserService,'get_by_telegram_id',AsyncMock(return_value=Obj(id=2,role=UserRole.TEACHER))),
                  patch.object(edit.UserService,'get_by_id',AsyncMock(return_value=Obj(name='Anna'))),
                  patch.object(edit.TeacherService,'get_by_user_id',AsyncMock(return_value=Obj(id=1))),
                  patch.object(edit.StudentService,'get_by_id',AsyncMock(return_value=Obj(id=9,teacher_id=1,user_id=3))),
                  patch.object(edit.ScheduleService,'get_by_id',AsyncMock(return_value=self.schedule)),
                  patch.object(edit.ScheduleService,'update_schedule',AsyncMock())]:
            p.start()
            self.addCleanup(p.stop)
    async def asyncTearDown(self):
        await self.storage.close()
    async def begin(self):
        await edit.begin_edit(self.callback,self.state)
    async def test_change_time_preserves_other_fields_until_save(self):
        await self.begin()
        self.callback.data='edit_field_time'
        await edit.choose_field(self.callback,self.state)
        await edit.enter_value(Obj(text='19:45'),self.state)
        self.assertEqual(self.schedule.start_time,time(18,30))
        edit.ScheduleService.update_schedule.assert_not_awaited()
        await edit.save_edit(self.callback,self.state)
        edit.ScheduleService.update_schedule.assert_awaited_once_with(self.session,self.schedule,
            day_of_week=1,start_time=time(19,45),duration_minutes=50,timezone='Europe/Warsaw',
            apply_future=False,expected=edit.values(self.schedule))
        self.assertIsNone(await self.state.get_state())
    async def test_cancel_does_not_write(self):
        await self.begin()
        await self.state.update_data(day_of_week=5)
        await clear_flow(self.state)
        edit.ScheduleService.update_schedule.assert_not_awaited()
        self.assertEqual(self.schedule.day_of_week,1)
    async def test_foreign_schedule_cannot_be_opened(self):
        self.schedule.teacher_id=99
        await self.begin()
        self.assertIsNone(await self.state.get_state())
    async def test_ownership_rechecked_before_save(self):
        await self.begin()
        self.schedule.teacher_id=99
        await edit.save_edit(self.callback,self.state)
        edit.ScheduleService.update_schedule.assert_not_awaited()
    async def test_external_change_is_not_overwritten(self):
        await self.begin()
        self.schedule.start_time=time(20)
        await edit.save_edit(self.callback,self.state)
        edit.ScheduleService.update_schedule.assert_not_awaited()
    async def test_invalid_time_and_duration_keep_draft(self):
        await self.begin()
        for field,raw in [('time','24:00'),('time',None),('duration','0'),('duration','1441'),('duration','1.5')]:
            await self.state.set_state(getattr(edit.EditScheduleState,field))
            await edit.enter_value(Obj(text=raw),self.state)
            self.assertEqual(await self.state.get_state(),getattr(edit.EditScheduleState,field).state)
        self.assertEqual((await self.state.get_data())['duration_minutes'],50)
    async def test_day_and_custom_duration(self):
        await self.begin()
        self.callback.data='edit_day_6'
        await edit.change_day(self.callback,self.state)
        await self.state.set_state(edit.EditScheduleState.duration)
        await edit.enter_value(Obj(text='75'),self.state)
        await edit.save_edit(self.callback,self.state)
        self.assertEqual(edit.ScheduleService.update_schedule.call_args.kwargs['duration_minutes'],75)
        self.assertEqual(edit.ScheduleService.update_schedule.call_args.kwargs['day_of_week'],6)
    async def test_database_error_retains_draft_for_retry(self):
        await self.begin()
        edit.ScheduleService.update_schedule.side_effect=SQLAlchemyError('test')
        await edit.save_edit(self.callback,self.state)
        self.assertEqual(await self.state.get_state(),edit.EditScheduleState.review.state)
        self.session.rollback.assert_awaited_once()
    async def test_back_and_duplicate_confirmation(self):
        await self.begin()
        await self.state.set_state(edit.EditScheduleState.time)
        await edit.back_to_review(self.callback,self.state)
        self.assertEqual((await self.state.get_data())['start_time'],'18:30:00')
        self.callback.data='edit_save'
        handler=next(h for h in edit.router.callback_query.handlers if h.callback is edit.save_edit)
        accepted,_=await handler.check(self.callback,raw_state=await self.state.get_state())
        self.assertTrue(accepted)
        await edit.save_edit(self.callback,self.state)
        accepted,_=await handler.check(self.callback,raw_state=await self.state.get_state())
        self.assertFalse(accepted)
