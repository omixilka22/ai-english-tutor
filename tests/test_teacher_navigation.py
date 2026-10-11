"""Teacher navigation regression tests; no external services."""
import unittest
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, patch
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from app.bot.handlers import lessons


class TeacherReturnTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=2))
        self.callback = Obj(data='teacher_list_return', from_user=Obj(id=2), answer=AsyncMock())

    async def test_return_reloads_week_instead_of_reusing_stale_lessons(self):
        await self.state.update_data(_teacher_list={'source': 'week_view_2026-10-12', 'index': 1, 'user': 2})
        async def reload(callback, state):
            self.assertEqual(callback.data, 'week_view_2026-10-12')
            await state.update_data(_pages=[{'text': 'fresh'}])
        with patch.object(lessons, 'AsyncSessionLocal', return_value=AsyncMock()), \
             patch('app.bot.handlers.schedules.teacher_for', new=AsyncMock()), \
             patch('app.bot.handlers.schedules.general_schedule', new=AsyncMock(side_effect=reload)) as view, \
             patch('app.bot.ui.show_page', new=AsyncMock()) as page:
            await lessons.return_to_teacher_list(self.callback, self.state)
            view.assert_awaited_once()
            page.assert_awaited_once_with(self.callback, self.state, 1)
        self.assertEqual(self.callback.data, 'teacher_list_return')

    async def test_return_rejects_other_users_saved_navigation(self):
        await self.state.update_data(_teacher_list={'source': 'general_schedule', 'index': 0, 'user': 99})
        with patch.object(lessons, 'AsyncSessionLocal', return_value=AsyncMock()), \
             patch('app.bot.handlers.schedules.teacher_for', new=AsyncMock()), \
             patch('app.bot.handlers.schedules.general_schedule', new=AsyncMock()) as view, \
             patch.object(lessons, 'show_screen', new=AsyncMock()):
            await lessons.return_to_teacher_list(self.callback, self.state)
            view.assert_not_awaited()
