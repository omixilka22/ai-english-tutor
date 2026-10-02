from test_materials import Obj, result
import unittest
from unittest.mock import AsyncMock, patch
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from app.services import material_notices as service
from app.database.models import UserRole

class NoticeTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_notice_id_saved(self):
        teacher=Obj(telegram_id=10,material_notice_id=None)
        bot=Obj(send_message=AsyncMock(return_value=Obj(message_id=100)))
        await service.publish_notice(AsyncMock(),bot,teacher,'ready',None)
        self.assertEqual(teacher.material_notice_id,100)
    async def test_existing_notice_updated_instead_of_added(self):
        teacher=Obj(telegram_id=10,material_notice_id=100)
        bot=Obj(send_message=AsyncMock(),edit_message_text=AsyncMock())
        await service.publish_notice(AsyncMock(),bot,teacher,'ready',None)
        bot.edit_message_text.assert_awaited_once();bot.send_message.assert_not_awaited()
    async def test_deleted_notice_replaced(self):
        teacher=Obj(telegram_id=10,material_notice_id=100)
        error=TelegramBadRequest(method=EditMessageText(text='x',chat_id=10,message_id=100),message='message to edit not found')
        bot=Obj(send_message=AsyncMock(return_value=Obj(message_id=101)),edit_message_text=AsyncMock(side_effect=error),delete_message=AsyncMock())
        await service.publish_notice(AsyncMock(),bot,teacher,'ready',None)
        self.assertEqual(teacher.material_notice_id,101)
    async def clean(self,user,event):
        session=AsyncMock();session.execute.return_value=result(user)
        context=AsyncMock();context.__aenter__.return_value=session
        with patch.object(service,'AsyncSessionLocal',return_value=context):
            await service.clean_notice(event)
        return session
    async def test_navigation_deletes_only_tracked_notice(self):
        user=Obj(role=UserRole.TEACHER,material_notice_id=100)
        event=Obj(from_user=Obj(id=10),data='material_7',bot=Obj(delete_message=AsyncMock()))
        await self.clean(user,event)
        event.bot.delete_message.assert_awaited_once_with(chat_id=10,message_id=100)
        self.assertIsNone(user.material_notice_id)
    async def test_clicking_legacy_notice_cleans_it_too(self):
        user=Obj(role=UserRole.TEACHER,material_notice_id=100)
        event=Obj(from_user=Obj(id=10),data='notification_material_7',message=Obj(message_id=99),bot=Obj(delete_message=AsyncMock()))
        await self.clean(user,event)
        self.assertEqual({call.kwargs['message_id'] for call in event.bot.delete_message.call_args_list},{99,100})
    async def test_student_pdf_and_notice_not_deleted(self):
        user=Obj(role=UserRole.STUDENT,material_notice_id=None)
        event=Obj(from_user=Obj(id=10),data='notification_material_7',message=Obj(message_id=99,document=Obj()),bot=Obj(delete_message=AsyncMock()))
        await self.clean(user,event)
        event.bot.delete_message.assert_not_awaited()
    async def test_network_error_keeps_id_for_next_navigation(self):
        user=Obj(role=UserRole.TEACHER,material_notice_id=100)
        event=Obj(from_user=Obj(id=10),data='home',bot=Obj(delete_message=AsyncMock(side_effect=TimeoutError())))
        with self.assertRaises(TimeoutError):await self.clean(user,event)
        self.assertEqual(user.material_notice_id,100)
