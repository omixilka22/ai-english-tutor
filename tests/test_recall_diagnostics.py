import unittest
from test_recall import client

class DiagnosticsTests(unittest.TestCase):
    def test_nested_validation_preserved(self):
        text=client.safe_error_detail({'recording_config':{'audio_separate_mp3':['This field may not be blank.']}})
        self.assertIn('recording_config.audio_separate_mp3',text)
        self.assertIn('This field may not be blank.',text)

    def test_reflected_inputs_urls_and_unknown_fields_removed(self):
        text=client.safe_error_detail({'detail':'Bad https://meet.google.com/abc-defg-hij for Private Name',
            'authorization':'secret','request_payload':{'message':'PRIVATE'}}, {'bot_name':'Private Name'})
        self.assertNotIn('meet.google.com',text)
        self.assertNotIn('Private Name',text)
        self.assertNotIn('secret',text)
        self.assertNotIn('PRIVATE',text)

    def test_bounded_and_plain_response_hidden(self):
        self.assertLessEqual(len(client.safe_error_detail({'detail':'x '*10000})),1200)
        self.assertNotIn('PRIVATE',client.safe_error_detail('<html>PRIVATE</html>'))
