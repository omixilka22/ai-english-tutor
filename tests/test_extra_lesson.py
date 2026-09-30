import os
import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock,MagicMock,patch
for k,v in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test','TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(k,v)
from aiogram import Bot
from aiogram.types import Message,Chat,User,Update,CallbackQuery
from aiogram.methods import SendMessage
from sqlalchemy.exc import SQLAlchemyError
from app.services.calendar_service import CalendarService
from app.services.notification_service import reminder_times
from app.database.models import LessonStatus
from app.bot.handlers import extra_lesson as ui

NOW=datetime(2030,1,1,8,tzinfo=timezone.utc)

class ExtraServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session=AsyncMock()
        self.session.add=MagicMock()
        response=MagicMock();response.scalar_one_or_none.return_value=None
        self.session.execute.return_value=response
        for p in [patch.object(CalendarService,'student_access',AsyncMock(return_value=(Obj(id=2,teacher_id=3),True))),patch('app.services.calendar_service.utcnow',return_value=NOW)]:
            p.start();self.addCleanup(p.stop)
    async def create(self,**kw):
        data=dict(scheduled_at=NOW+timedelta(days=2),duration_minutes=75,timezone_name='Europe/Kyiv')
        data.update(kw)
        return await CalendarService.create_extra(self.session,100,2,**data)
    async def test_one_off_has_no_recurrence_and_keeps_duration(self):
        item=await self.create()
        self.assertIsNone(item.schedule_id)
        self.assertIsNone(item.occurrence_week)
        self.assertTrue(item.is_exception)
        self.assertEqual(item.duration_minutes,75)
        self.assertEqual(item.student_id,2)
        self.assertEqual(item.teacher_id,3)
        self.assertEqual(item.status,LessonStatus.SCHEDULED)
        self.session.add.assert_called_once_with(item)
        self.session.commit.assert_awaited_once()
        self.assertEqual([k for k,_,_ in reminder_times(item,NOW)],['reminder_12h','reminder_1h'])
    async def test_short_notice_skips_elapsed_reminders(self):
        item=await self.create(scheduled_at=NOW+timedelta(minutes=30))
        self.assertEqual(reminder_times(item,NOW),[])
    async def test_wrong_owner_or_student_role_rejected(self):
        CalendarService.student_access.side_effect=ValueError('Access denied')
        with self.assertRaises(ValueError):await self.create()
        self.session.add.assert_not_called()
    async def test_past_naive_date_and_invalid_duration_rejected(self):
        for kw in [dict(scheduled_at=NOW),dict(scheduled_at=datetime(2030,1,5)),dict(duration_minutes=0),dict(duration_minutes=1441),dict(timezone_name='Missing/Zone')]:
            with self.subTest(kw=kw),self.assertRaises(ValueError):await self.create(**kw)
        self.session.commit.assert_not_awaited()
    async def test_duplicate_start_does_not_create_another_lesson(self):
        self.session.execute.return_value.scalar_one_or_none.return_value=5
        with self.assertRaises(ValueError):await self.create()
        self.session.add.assert_not_called()

class ExtraDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.bot import bot as app
        self.app=app;self.bot=Bot('123456:TEST_TOKEN')
        self.user=User(id=150,is_bot=False,first_name='Teacher')
        self.state=app.dp.fsm.get_context(bot=self.bot,chat_id=150,user_id=150)
        await self.state.clear()
        async def request(bot,method,**kwargs):
            return self.message(100,method.text) if isinstance(method,SendMessage) else True
        self.bot.session=AsyncMock(side_effect=request)
        for p in [patch.object(ui,'AsyncSessionLocal',return_value=AsyncMock()),
                  patch.object(ui.CalendarService,'student_access',AsyncMock(return_value=(Obj(id=2,user_id=3),True))),
                  patch.object(ui.UserService,'get_by_id',AsyncMock(return_value=Obj(name='Anna'))),
                  patch.object(ui.CalendarService,'create_extra',AsyncMock(return_value=Obj(id=7)))]:
            p.start();self.addCleanup(p.stop)
    async def asyncTearDown(self):await self.state.clear()
    def message(self,id,text):
        return Message(message_id=id,date=datetime.now(timezone.utc),chat=Chat(id=150,type='private'),from_user=self.user,text=text)
    async def click(self,data):
        await self.app.dp.feed_update(self.bot,Update(update_id=1,callback_query=CallbackQuery(id='1',from_user=self.user,chat_instance='test',message=self.message(100,'Menu'),data=data)))
    async def text(self,text):
        await self.app.dp.feed_update(self.bot,Update(update_id=2,message=self.message(2,text)))
    async def prepare(self):
        await self.click('extra_lesson_2')
        await self.text('10.11.2030 18:30')
        await self.click('extra_duration_60')
        self.assertEqual(await self.state.get_state(),ui.ExtraLesson.confirm.state)
    async def test_confirm_creates_once_and_clears_draft(self):
        await self.prepare()
        ui.CalendarService.create_extra.assert_not_awaited()
        await self.click('extra_confirm');await self.click('extra_confirm')
        ui.CalendarService.create_extra.assert_awaited_once()
        self.assertEqual(ui.CalendarService.create_extra.call_args.kwargs['scheduled_at'].hour,16)
        self.assertIsNone(await self.state.get_state())
    async def test_back_allows_change_of_duration(self):
        await self.prepare();await self.click('extra_back')
        self.assertEqual(await self.state.get_state(),ui.ExtraLesson.duration.state)
        await self.text('75');await self.click('extra_confirm')
        self.assertEqual(ui.CalendarService.create_extra.call_args.kwargs['duration_minutes'],75)
    async def test_invalid_inputs_stay_in_current_step(self):
        await self.click('extra_lesson_2')
        for text in ['30.02.2030 18:30','01.01.2020 18:30','photo']:
            await self.text(text)
            self.assertEqual(await self.state.get_state(),ui.ExtraLesson.date.state)
        await self.text('10.11.2030 18:30')
        for text in ['0','1441','9'*5000,'abc']:
            await self.text(text)
            self.assertEqual(await self.state.get_state(),ui.ExtraLesson.duration.state)
        ui.CalendarService.create_extra.assert_not_awaited()
    async def test_cancel_command_does_not_create(self):
        await self.prepare()
        with patch.object(self.app,'show_home',AsyncMock()) as home:
            await self.text('/cancel')
            home.assert_awaited_once()
        ui.CalendarService.create_extra.assert_not_awaited()
    async def test_permission_rejection_does_not_start_wizard(self):
        ui.CalendarService.student_access.side_effect=ValueError('Access denied')
        await self.click('extra_lesson_2')
        self.assertIsNone(await self.state.get_state())
    async def test_database_failure_preserves_draft_for_retry(self):
        await self.prepare()
        ui.CalendarService.create_extra.side_effect=SQLAlchemyError('test')
        await self.click('extra_confirm')
        self.assertEqual(await self.state.get_state(),ui.ExtraLesson.confirm.state)
