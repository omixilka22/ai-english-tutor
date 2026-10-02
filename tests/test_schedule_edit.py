import os
import unittest
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, patch
for k,v in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test','TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(k,v)
from app.bot.handlers import schedule_edit

class RetiredTemplateTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_button_clears_draft_and_returns_to_weekly_navigation(self):
        callback = Obj(answer=AsyncMock())
        state = AsyncMock()
        with patch.object(schedule_edit, 'clear_flow', AsyncMock()) as clear, patch.object(schedule_edit, 'show_screen', AsyncMock()) as show:
            await schedule_edit.stale_edit(callback, state)
        clear.assert_awaited_once_with(state)
        self.assertIn('конкретних занять', show.call_args.args[2])
