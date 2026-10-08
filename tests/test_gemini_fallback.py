import unittest
from unittest.mock import patch
import test_materials
from app.services import gemini_analysis as ai

class FallbackTests(unittest.TestCase):
    def test_only_final_transient_attempt_switches(self):
        with patch.object(ai.settings,'GEMINI_FALLBACK_MODEL','reserve'),patch.object(ai.settings,'GEMINI_MODEL','primary'):
            for attempt in (1,2): self.assertIsNone(ai.fallback_for_attempt(attempt,'http_503'))
            for code in ai.TRANSIENT_ERRORS: self.assertEqual(ai.fallback_for_attempt(3,code),'reserve')
            for code in ('credentials','quota','invalid_request','invalid_response','missing_key',None):
                self.assertIsNone(ai.fallback_for_attempt(3,code))

    def test_blank_or_same_model_disables_switch(self):
        for value in ('',ai.settings.GEMINI_MODEL):
            with patch.object(ai.settings,'GEMINI_FALLBACK_MODEL',value):
                self.assertIsNone(ai.fallback_for_attempt(3,'http_503'))
