import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from io import BytesIO
from importlib.util import find_spec
from app.services.lesson_pdf import build_lesson_pdf
from app.services.analysis_content import BLOCKS

@unittest.skipUnless(find_spec('reportlab') and find_spec('pypdf'), 'PDF verification needs reportlab and pypdf')
class PdfTests(unittest.TestCase):
    def render(self,content):
        from pypdf import PdfReader
        lesson=SimpleNamespace(id=5,scheduled_at=datetime(2026,10,1,15,tzinfo=timezone.utc),timezone='Europe/Kyiv')
        data=build_lesson_pdf(lesson,content,student_name='Марія',teacher_name='Олександр')
        self.assertTrue(data.startswith(b'%PDF-'))
        return PdfReader(BytesIO(data))
    def test_all_blocks_unicode_and_literal_markup(self):
        content={key:f'{key}: Українська ґ є і ї. <b>Literal</b> & text.' for key in BLOCKS}
        reader=self.render(content)
        text='\n'.join(p.extract_text() for p in reader.pages)
        for key,value in content.items():self.assertIn(value,text)
        self.assertIn('Марія',text)
        self.assertIn('Олександр',text)
        self.assertIn('18:00',text)
    def test_maximum_content_is_not_truncated(self):
        content={key:('Речення для перевірки перенесення. '*75)+f' END_{key}' for key in BLOCKS}
        reader=self.render(content)
        self.assertGreater(len(reader.pages),1)
        text='\n'.join(p.extract_text() for p in reader.pages)
        for key in BLOCKS:self.assertIn(f'END_{key}',text)
    def test_unbroken_text_wraps(self):
        content={key:'X'*2700+f' END_{key}' for key in BLOCKS}
        reader=self.render(content)
        text='\n'.join(p.extract_text() for p in reader.pages)
        for key in BLOCKS:self.assertIn(f'END_{key}',text)
