from test_notifications import NOW, lesson, job, recipient, result, Obj
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from app.database.models import UserRole, User, Teacher, LessonNotification
from app.services import meeting_service as service, notification_service as notifications
from app.workers import notifications as worker

URL='https://meet.google.com/abc-defg-hij'

class MeetingTests(unittest.IsolatedAsyncioTestCase):
    def test_url_validation(self):
        self.assertEqual(service.normalize_meeting_url(' '+URL+'\n'),URL)
        for value in ['http://meet.google.com/abc-defg-hij',URL+'?x=1',URL+'.evil.com','javascript:alert(1)','https://evil.com/abc-defg-hij','']:
            with self.assertRaises(ValueError):service.normalize_meeting_url(value)
    def test_old_teacher_link_hidden(self):
        self.assertIsNone(service.meeting_url(recipient(meeting_url=URL,meeting_teacher_id=99)))
    async def test_save_replace_remove(self):
        student=recipient();session=AsyncMock();session.execute.return_value=result(student)
        with patch.object(service.CalendarService,'student_access',AsyncMock(return_value=(student,True))):
            for value in [URL,'https://meet.google.com/xyz-abcd-efg',None]:
                await service.save_meeting_url(session,100,2,value)
                self.assertEqual(student.meeting_url,value)
                self.assertEqual(student.meeting_teacher_id,3 if value else None)
    async def test_wrong_owner_cannot_save(self):
        session=AsyncMock()
        with patch.object(service.CalendarService,'student_access',AsyncMock(side_effect=ValueError('Denied'))):
            with self.assertRaises(ValueError):await service.save_meeting_url(session,100,2,URL)
        session.commit.assert_not_awaited()
    async def test_reassignment_during_edit_rejected(self):
        session=AsyncMock();session.execute.return_value=result(recipient(teacher_id=99))
        with patch.object(service.CalendarService,'student_access',AsyncMock(return_value=(recipient(),True))):
            with self.assertRaises(ValueError):await service.save_meeting_url(session,100,2,URL)
        session.commit.assert_not_awaited()
    def test_teacher_times_and_short_notice(self):
        times=notifications.reminder_times(lesson(),NOW,teacher=True)
        self.assertEqual([(k,d) for k,d,_ in times],[('teacher_reminder_1h',NOW+timedelta(hours=11)),('teacher_link_15m',NOW+timedelta(hours=11,minutes=45))])
        times=notifications.reminder_times(lesson(scheduled_at=NOW+timedelta(minutes=30),notification_since=NOW),NOW,teacher=True)
        self.assertEqual([k for k,_,_ in times],['teacher_link_15m'])
    def test_link_only_in_requested_reminders(self):
        student=recipient(meeting_url=URL,meeting_teacher_id=3)
        for kind in ['reminder_12h','reminder_1h','teacher_reminder_1h','teacher_link_15m']:
            text,markup=worker.notification_content(job(kind=kind),lesson(),NOW,student,'Anna')
            urls=[b.url for row in markup.inline_keyboard for b in row if b.url]
            self.assertEqual(urls,[URL] if kind in ['reminder_1h','teacher_link_15m'] else [])
            if kind.startswith('teacher_'):self.assertIn('Anna',text)
    def test_missing_link_offers_teacher_action(self):
        text,markup=worker.notification_content(job(kind='teacher_link_15m'),lesson(),NOW,recipient(),'Anna')
        self.assertIn('ще не додано',text)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data,'notification_meet_2')
    def test_teacher_not_disabled_by_student_toggle(self):
        self.assertIsNone(notifications.invalid_reason(job(kind='teacher_reminder_1h'),lesson(),recipient(reminders_enabled=False),Obj(id=7,role=UserRole.TEACHER),NOW,teacher=Obj(id=3,user_id=7)))
    def test_teacher_stale_cancelled_deleted_reassigned_skipped(self):
        from app.database.models import LessonStatus
        for item in [lesson(notification_version=2),lesson(status=LessonStatus.CANCELLED),lesson(is_deleted=True),lesson(teacher_id=99)]:
            self.assertIsNotNone(notifications.invalid_reason(job(kind='teacher_link_15m'),item,recipient(),Obj(id=7,role=UserRole.TEACHER),NOW,teacher=Obj(id=3,user_id=7)))
    async def test_delivery_goes_to_teacher_and_deduplicates(self):
        item=lesson();notice=job(kind='teacher_link_15m');student=recipient(meeting_url=URL,meeting_teacher_id=3)
        session=AsyncMock()
        def get(cls,key):
            if cls is LessonNotification:return notice
            if cls is Teacher:return Obj(id=3,user_id=7)
            return Obj(id=key,telegram_id=200 if key==7 else 100,name='Anna',role=UserRole.TEACHER if key==7 else UserRole.STUDENT)
        session.get.side_effect=get
        session.execute.side_effect=lambda stmt:result(item if 'FROM lessons' in str(stmt) else student if 'FROM students' in str(stmt) else notice)
        context=AsyncMock();context.__aenter__.return_value=session
        bot=Obj(send_message=AsyncMock(return_value=Obj(message_id=42)))
        with patch.object(worker,'AsyncSessionLocal',return_value=context),patch.object(worker,'utcnow',return_value=NOW):
            await worker.deliver_one(bot,9)
            await worker.deliver_one(bot,9)
        bot.send_message.assert_awaited_once()
        self.assertEqual(bot.send_message.call_args.kwargs['chat_id'],200)
        self.assertEqual(bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard[0][0].url,URL)

from aiogram import Bot
from aiogram.types import Message,Chat,User,Update,CallbackQuery
from aiogram.methods import SendMessage
from datetime import datetime,timezone
from app.bot.handlers import meeting as ui
class MeetingDispatchTests(unittest.IsolatedAsyncioTestCase):
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
                  patch.object(ui.CalendarService,'student_access',AsyncMock(return_value=(Obj(id=2,user_id=3,teacher_id=3),True))),
                  patch.object(ui,'save_meeting_url',AsyncMock())]:
            p.start();self.addCleanup(p.stop)
    async def asyncTearDown(self):await self.state.clear()
    def message(self,id,text):
        return Message(message_id=id,date=datetime.now(timezone.utc),chat=Chat(id=150,type='private'),from_user=self.user,text=text)
    async def click(self,data):
        await self.app.dp.feed_update(self.bot,Update(update_id=1,callback_query=CallbackQuery(id='1',from_user=self.user,chat_instance='test',message=self.message(100,'Menu'),data=data)))
    async def text(self,text):
        await self.app.dp.feed_update(self.bot,Update(update_id=2,message=self.message(2,text)))

    async def test_save_and_back(self):
        await self.click('meet_2')
        await self.click('meet_edit_2')
        self.assertEqual(await self.state.get_state(),ui.Meeting.url.state)
        await self.text(URL)
        ui.save_meeting_url.assert_awaited_once()
        self.assertEqual(ui.save_meeting_url.call_args.args[1:],(150,2,URL))
        self.assertIsNone(await self.state.get_state())
    async def test_remove_confirmation_and_stale_click(self):
        await self.click('meet_remove_2')
        ui.save_meeting_url.assert_not_awaited()
        await self.click('meet_remove_confirm')
        await self.click('meet_remove_confirm')
        ui.save_meeting_url.assert_awaited_once()
        self.assertIsNone(ui.save_meeting_url.call_args.args[-1])
    async def test_back_cancels_input(self):
        await self.click('meet_edit_2')
        await self.click('meet_2')
        self.assertIsNone(await self.state.get_state())
        ui.save_meeting_url.assert_not_awaited()
