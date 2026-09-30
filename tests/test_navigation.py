import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

for name,value in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test',
                    'TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(name,value)

from aiogram import Bot
from aiogram.types import CallbackQuery, Message, Chat, User, Update
from aiogram.methods import SendMessage, EditMessageText, DeleteMessage, AnswerCallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from app.bot.ui import show_screen, clear_flow, paginated_screen, show_page, navigation
from app.bot.handlers import schedules
from app.bot.states.schedule import ScheduleState


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot=Bot('123456:TEST_TOKEN')
        self.storage=MemoryStorage()
        self.state=FSMContext(self.storage,StorageKey(bot_id=self.bot.id,chat_id=2,user_id=2))
        self.user=User(id=2,is_bot=False,first_name='Test')
        self.msg=Message(message_id=10,date=datetime.now(timezone.utc),chat=Chat(id=2,type='private'),
                         from_user=self.user,text='18:30').as_(self.bot)
        self.callback=CallbackQuery(id='cb',from_user=self.user,chat_instance='test',message=self.msg,data='home').as_(self.bot)
        self.bot.edit_message_text=AsyncMock()
        self.bot.send_message=AsyncMock(return_value=self.msg.model_copy(update={'message_id':20}))
        self.bot.delete_message=AsyncMock()

    async def asyncTearDown(self):
        await self.bot.session.close()
        await self.storage.close()

    async def test_callback_edits_without_new_message(self):
        await show_screen(self.callback,self.state,'Menu')
        self.bot.edit_message_text.assert_awaited_once()
        self.bot.send_message.assert_not_awaited()
        self.assertEqual((await self.state.get_data())['_screen_id'],10)

    async def test_typed_input_deleted_existing_screen_edited(self):
        await self.state.update_data(_screen_id=5)
        await show_screen(self.msg,self.state,'Duration')
        self.bot.delete_message.assert_awaited_once_with(chat_id=2,message_id=10)
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['message_id'],5)
        self.bot.send_message.assert_not_awaited()

    async def test_navigation_commands_are_kept_and_menu_is_sent_at_bottom(self):
        for text in ['/start','/start invite-token','/start@TutorBot invite-token','/menu','/cancel']:
            with self.subTest(text=text):
                self.bot.delete_message.reset_mock()
                self.bot.send_message.reset_mock()
                self.bot.edit_message_text.reset_mock()
                await self.state.update_data(_screen_id=5)
                message=self.msg.model_copy(update={'text':text}).as_(self.bot)
                await show_screen(message,self.state,'Home')
                self.bot.send_message.assert_awaited_once()
                self.bot.edit_message_text.assert_not_awaited()
                self.bot.delete_message.assert_awaited_once_with(chat_id=2,message_id=5)
                self.assertEqual((await self.state.get_data())['_screen_id'],20)

    async def test_start_without_existing_menu_survives(self):
        await show_screen(self.msg.model_copy(update={'text':'/start'}).as_(self.bot),self.state,'Home')
        self.bot.delete_message.assert_not_awaited()
        self.bot.send_message.assert_awaited_once()

    async def test_send_failure_keeps_start_and_previous_menu(self):
        await self.state.update_data(_screen_id=5)
        self.bot.send_message.side_effect=RuntimeError('network unavailable')
        with self.assertRaises(RuntimeError):
            await show_screen(self.msg.model_copy(update={'text':'/start'}).as_(self.bot),self.state,'Home')
        self.bot.delete_message.assert_not_awaited()
        self.assertEqual((await self.state.get_data())['_screen_id'],5)

    async def test_notification_button_preserves_notice_and_active_menu(self):
        await self.state.update_data(_screen_id=5)
        callback=self.callback.model_copy(update={'data':'notification_lesson_10'}).as_(self.bot)
        await show_screen(callback,self.state,'Lesson')
        self.bot.edit_message_text.assert_awaited_once()
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['message_id'],5)
        self.bot.delete_message.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()

    async def test_notification_after_restart_creates_menu_without_deleting_notice(self):
        callback=self.callback.model_copy(update={'data':'notification_list'}).as_(self.bot)
        await show_screen(callback,self.state,'Lessons')
        self.bot.send_message.assert_awaited_once()
        self.bot.edit_message_text.assert_not_awaited()
        self.bot.delete_message.assert_not_awaited()

    async def test_not_modified_does_not_duplicate(self):
        self.bot.edit_message_text.side_effect=TelegramBadRequest(method=EditMessageText(text='Menu'),message='Bad Request: message is not modified')
        await show_screen(self.callback,self.state,'Menu')
        self.bot.send_message.assert_not_awaited()

    async def test_missing_screen_replaced(self):
        self.bot.edit_message_text.side_effect=TelegramBadRequest(method=EditMessageText(text='Menu'),message='message to edit not found')
        await show_screen(self.callback,self.state,'Menu')
        self.bot.send_message.assert_awaited_once()
        self.assertEqual((await self.state.get_data())['_screen_id'],20)

    async def test_delete_failure_does_not_break_ui(self):
        self.bot.delete_message.side_effect=TelegramBadRequest(method=DeleteMessage(chat_id=2,message_id=10),message="message can't be deleted")
        await show_screen(self.msg,self.state,'Menu')
        self.bot.send_message.assert_awaited_once()

    async def test_reset_keeps_screen_but_discards_draft(self):
        await self.state.update_data(_screen_id=5,student_id=9,_pages=[{}])
        await self.state.set_state(ScheduleState.confirming)
        await clear_flow(self.state)
        self.assertEqual(await self.state.get_data(),{'_screen_id':5})
        self.assertIsNone(await self.state.get_state())

    async def test_long_list_is_paged_in_same_message(self):
        await paginated_screen(self.callback,self.state,'Students',rows=[[(f'Name {i}',f'student_{i}')] for i in range(19)],footer=navigation('schedule_menu'))
        self.assertEqual(len((await self.state.get_data())['_pages']),3)
        await show_page(self.callback,self.state,1)
        kwargs=self.bot.edit_message_text.call_args.kwargs
        self.assertIn('2 / 3',kwargs['text'])
        buttons=[b.callback_data for row in kwargs['reply_markup'].inline_keyboard for b in row]
        self.assertIn('student_8',buttons)
        self.assertNotIn('student_0',buttons)
        self.assertIn('schedule_menu',buttons)
        self.assertIn('home',buttons)
        self.bot.send_message.assert_not_awaited()

    async def test_wizard_back_keeps_previous_values(self):
        await self.state.update_data(student_id=9,student_name='Anna',day_of_week=2,start_time='18:30',duration_minutes=60)
        await self.state.set_state(ScheduleState.confirming)
        callback=SimpleNamespace(answer=AsyncMock())
        with patch.object(schedules,'show_screen',AsyncMock()) as screen:
            for expected in [ScheduleState.choosing_duration,ScheduleState.waiting_for_time,ScheduleState.choosing_day]:
                await schedules.schedule_back(callback,self.state)
                self.assertEqual(await self.state.get_state(),expected.state)
            self.assertIn('Anna',screen.call_args.args[2])
            self.assertEqual((await self.state.get_data())['start_time'],'18:30')


class DispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_and_cancel_remain_visible_and_reopen_menu(self):
        from app.bot import bot as app
        from app.database.models import UserRole
        client=Bot('123456:TEST_TOKEN')
        user=User(id=88,is_bot=False,first_name='Test')
        requests=[]
        def message(id,text):
            return Message(message_id=id,date=datetime.now(timezone.utc),chat=Chat(id=88,type='private'),from_user=user,text=text)
        async def request(bot,method,**kwargs):
            requests.append(method)
            if isinstance(method,SendMessage):
                return message(100,method.text)
            return True
        client.session=AsyncMock(side_effect=request)
        ctx=AsyncMock()
        user_record=SimpleNamespace(id=88,role=UserRole.TEACHER,name='Teacher')
        state=app.dp.fsm.get_context(bot=client,chat_id=88,user_id=88)
        await state.clear()
        with patch.object(app,'AsyncSessionLocal',return_value=ctx),patch.object(app.UserService,'get_by_telegram_id',AsyncMock(return_value=user_record)):
            await app.dp.feed_update(client,Update(update_id=1,message=message(1,'/start')))
            callback=CallbackQuery(id='c1',from_user=user,chat_instance='test',message=message(100,'Menu'),data='change_to_teacher')
            await app.dp.feed_update(client,Update(update_id=2,callback_query=callback))
            self.assertIsNotNone(await state.get_state())
            await app.dp.feed_update(client,Update(update_id=3,message=message(2,'bad code')))
            await app.dp.feed_update(client,Update(update_id=4,message=message(3,'/cancel')))
            self.assertIsNone(await state.get_state())
            self.assertEqual(sum(isinstance(m,SendMessage) for m in requests),2)
            self.assertGreaterEqual(sum(isinstance(m,EditMessageText) for m in requests),2)
            self.assertEqual({m.message_id for m in requests if isinstance(m,DeleteMessage)},{2})
        await state.clear()

    async def test_persistent_telegram_command_menu_is_configured(self):
        from app.bot.bot import configure_navigation
        client=SimpleNamespace(set_my_commands=AsyncMock(),set_chat_menu_button=AsyncMock())
        await configure_navigation(client)
        commands=client.set_my_commands.call_args.args[0]
        self.assertEqual([item.command for item in commands],['start','menu','cancel'])
        self.assertEqual(client.set_chat_menu_button.call_args.kwargs['menu_button'].type,'commands')

    async def test_schedule_dispatch_back_save_and_duplicate(self):
        from app.bot import bot as app
        from app.database.models import UserRole
        client=Bot('123456:TEST_TOKEN')
        user=User(id=89,is_bot=False,first_name='Test')
        requests=[]
        def message(id,text):
            return Message(message_id=id,date=datetime.now(timezone.utc),chat=Chat(id=89,type='private'),from_user=user,text=text)
        async def request(bot,method,**kwargs):
            requests.append(method)
            return message(100,method.text) if isinstance(method,SendMessage) else True
        client.session=AsyncMock(side_effect=request)
        state=app.dp.fsm.get_context(bot=client,chat_id=89,user_id=89)
        await state.clear()
        counter=0
        async def click(data):
            nonlocal counter
            counter+=1
            await app.dp.feed_update(client,Update(update_id=counter,callback_query=CallbackQuery(
                id=str(counter),from_user=user,chat_instance='test',message=message(100,'Screen'),data=data)))
        ctx=AsyncMock()
        patches=[patch.object(schedules,'AsyncSessionLocal',return_value=ctx),
                 patch.object(schedules.UserService,'get_by_telegram_id',AsyncMock(return_value=SimpleNamespace(id=89,role=UserRole.TEACHER))),
                 patch.object(schedules.TeacherService,'get_by_user_id',AsyncMock(return_value=SimpleNamespace(id=1))),
                 patch.object(schedules.StudentService,'get_by_id',AsyncMock(return_value=SimpleNamespace(id=9,user_id=90,teacher_id=1))),
                 patch.object(schedules.UserService,'get_by_id',AsyncMock(return_value=SimpleNamespace(name='Anna'))),
                 patch.object(schedules.ScheduleService,'create_schedule',AsyncMock())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        await click('add_schedule_9')
        await click('schedule_day_1')
        await app.dp.feed_update(client,Update(update_id=99,message=message(5,'18:30')))
        await click('schedule_duration_60')
        await click('schedule_back')
        self.assertEqual(await state.get_state(),ScheduleState.choosing_duration.state)
        await click('schedule_duration_90')
        await click('schedule_confirm')
        await click('schedule_confirm')
        schedules.ScheduleService.create_schedule.assert_awaited_once()
        self.assertEqual(schedules.ScheduleService.create_schedule.call_args.kwargs['duration_minutes'],90)
        self.assertIsNone(await state.get_state())
        self.assertEqual((await state.get_data())['_screen_id'],100)
        self.assertEqual(sum(isinstance(m,SendMessage) for m in requests),0)
        self.assertIn(5,[m.message_id for m in requests if isinstance(m,DeleteMessage)])
        await state.clear()

if __name__=='__main__':
    unittest.main()
