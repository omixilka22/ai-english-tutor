import os
import unittest
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock,patch
for k,v in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test','TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(k,v)
from aiogram import Bot
from aiogram.types import Message,Chat,User,Update,CallbackQuery
from aiogram.methods import SendMessage
from app.bot.handlers import lessons as ui
from app.database.models import LessonStatus

class LessonDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.bot import bot as app
        self.app=app
        self.bot=Bot('123456:TEST_TOKEN')
        self.user=User(id=120,is_bot=False,first_name='Teacher')
        self.state=app.dp.fsm.get_context(bot=self.bot,chat_id=120,user_id=120)
        await self.state.clear()
        self.requests=[]
        async def request(bot,method,**kwargs):
            self.requests.append(method)
            return self.message(100,method.text) if isinstance(method,SendMessage) else True
        self.bot.session=AsyncMock(side_effect=request)
        self.lesson=Obj(id=1,student_id=2,scheduled_at=datetime.now(timezone.utc)+timedelta(days=3),
                        timezone='Europe/Kyiv',duration_minutes=60,status=LessonStatus.SCHEDULED)
        for p in [patch.object(ui,'AsyncSessionLocal',return_value=AsyncMock()),
                  patch.object(ui.CalendarService,'lesson_access',AsyncMock(return_value=(self.lesson,True))),
                  patch.object(ui.CalendarService,'restore_lesson',AsyncMock()),
                  patch.object(ui.CalendarService,'delete_lesson',AsyncMock()),
                  patch.object(ui.CalendarService,'change_lesson',AsyncMock())]:
            p.start(); self.addCleanup(p.stop)
    async def asyncTearDown(self):
        await self.state.clear()
    def message(self,id,text):
        return Message(message_id=id,date=datetime.now(timezone.utc),chat=Chat(id=120,type='private'),from_user=self.user,text=text)
    async def click(self,data):
        await self.app.dp.feed_update(self.bot,Update(update_id=1,callback_query=CallbackQuery(
            id='1',from_user=self.user,chat_instance='test',message=self.message(100,'Screen'),data=data)))
    async def test_move_confirm_and_double_click(self):
        await self.click('move_lesson_1')
        self.assertEqual(await self.state.get_state(),ui.LessonEdit.date.state)
        await self.app.dp.feed_update(self.bot,Update(update_id=2,message=self.message(2,'10.11.2030 18:30')))
        self.assertEqual(await self.state.get_state(),ui.LessonEdit.confirm.state)
        await self.click('lesson_move_confirm')
        await self.click('lesson_move_confirm')
        ui.CalendarService.change_lesson.assert_awaited_once()
        self.assertEqual(ui.CalendarService.change_lesson.call_args.kwargs['scheduled_at'].hour,16)
        self.assertIsNone(await self.state.get_state())
    async def test_cancel_requires_confirmation(self):
        await self.click('cancel_lesson_1')
        ui.CalendarService.change_lesson.assert_not_awaited()
        await self.click('lesson_cancel_confirm')
        self.assertTrue(ui.CalendarService.change_lesson.call_args.kwargs['cancel'])
    async def test_back_discards_move_without_saving(self):
        await self.click('move_lesson_1')
        await self.click('lesson_1')
        self.assertIsNone(await self.state.get_state())
        ui.CalendarService.change_lesson.assert_not_awaited()
    async def test_invalid_date_keeps_input_state(self):
        await self.click('move_lesson_1')
        await self.app.dp.feed_update(self.bot,Update(update_id=2,message=self.message(2,'30.02.2030 18:30')))
        self.assertEqual(await self.state.get_state(),ui.LessonEdit.date.state)
        ui.CalendarService.change_lesson.assert_not_awaited()

    async def test_restore_requires_confirmation_and_ignores_double_click(self):
        self.lesson.status=LessonStatus.CANCELLED
        await self.click('restore_lesson_1')
        ui.CalendarService.restore_lesson.assert_not_awaited()
        self.assertEqual(await self.state.get_state(),ui.LessonEdit.restore.state)
        await self.click('lesson_restore_confirm')
        await self.click('lesson_restore_confirm')
        ui.CalendarService.restore_lesson.assert_awaited_once()

    async def test_delete_requires_confirmation_and_returns_to_list(self):
        await self.click('delete_lesson_1')
        ui.CalendarService.delete_lesson.assert_not_awaited()
        await self.click('lesson_delete_confirm')
        await self.click('lesson_delete_confirm')
        ui.CalendarService.delete_lesson.assert_awaited_once()
        screens=[r for r in self.requests if getattr(r,'reply_markup',None)]
        buttons=[b.callback_data for row in screens[-1].reply_markup.inline_keyboard for b in row]
        self.assertIn('student_lessons_2',buttons)

    async def test_back_discards_deletion(self):
        await self.click('delete_lesson_1')
        await self.click('lesson_1')
        ui.CalendarService.delete_lesson.assert_not_awaited()
        self.assertIsNone(await self.state.get_state())

    async def test_student_has_no_restore_or_delete_buttons(self):
        self.lesson.status=LessonStatus.CANCELLED
        ui.CalendarService.lesson_access.return_value=(self.lesson,False)
        await self.click('lesson_1')
        screens=[r for r in self.requests if getattr(r,'reply_markup',None)]
        buttons=[b.callback_data for row in screens[-1].reply_markup.inline_keyboard for b in row]
        self.assertNotIn('restore_lesson_1',buttons)
        self.assertNotIn('delete_lesson_1',buttons)

    async def test_confirmation_only_after_end(self):
        now=datetime.now(timezone.utc)
        self.lesson.scheduled_at=now-timedelta(minutes=5)
        with patch.object(ui,'utcnow',return_value=now),patch.object(ui,'show_screen',AsyncMock()) as screen:
            await self.click('lesson_1')
            callbacks=[b.callback_data for row in screen.call_args.kwargs['reply_markup'].inline_keyboard for b in row]
            self.assertNotIn('attendance_yes_1',callbacks)
            self.assertIn('Триває',screen.call_args.args[2])
            self.assertNotIn('не підтверджено',screen.call_args.args[2])
            self.lesson.scheduled_at=now-timedelta(minutes=60)
            await self.click('lesson_1')
            callbacks=[b.callback_data for row in screen.call_args.kwargs['reply_markup'].inline_keyboard for b in row]
            self.assertIn('attendance_yes_1',callbacks)
            self.assertIn('attendance_no_1',callbacks)
    async def test_completed_history_detail_returns_to_history(self):
        self.lesson.conducted_at=datetime.now(timezone.utc)
        self.lesson.status=LessonStatus.COMPLETED
        with patch.object(ui,'show_screen',AsyncMock()) as screen:
            await self.click('history_lesson_1')
            callbacks=[b.callback_data for row in screen.call_args.kwargs['reply_markup'].inline_keyboard for b in row]
            self.assertIn('lesson_history_2',callbacks)
            self.assertIn('material_1',callbacks)
            self.assertIn('Проведено',screen.call_args.args[2])
