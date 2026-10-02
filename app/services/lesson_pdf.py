"""Render the teacher-approved four blocks in memory, with embedded Cyrillic fonts."""
from io import BytesIO
import re
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo
from app.services.analysis_content import BLOCKS, validate_content

FONT_DIR = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'
_FONT_LOCK = Lock()


class PdfGenerationError(Exception):
    pass


def build_lesson_pdf(lesson, content, *, student_name='', teacher_name=''):
    # Lazy imports let the rest of the bot work if the new dependency is missing.
    try:
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    except ImportError:
        raise PdfGenerationError('pdf_dependency_missing') from None
    try:
        blocks = validate_content(content)
        with _FONT_LOCK:
            for name, filename in [('LessonRegular', 'DejaVuSans.ttf'), ('LessonBold', 'DejaVuSans-Bold.ttf')]:
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))
        glyphs = pdfmetrics.getFont('LessonRegular').face.charToGlyph

        def safe(text):
            # Export Telegram symbols as words where the bundled font lacks them.
            text = str(text).replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ')
            for old, new in {'✅': 'Правильно:', '❌': 'Помилка:', '\ufe0f': '', '\u200d': '',
                             '\u2011': '-', '\u2013': '-', '\u2014': '-'}.items():
                text = text.replace(old, new)
            text = ''.join(c if c == '\n' or ord(c) in glyphs else f'[U+{ord(c):04X}]' for c in text)
            return escape(text).replace('\n', '<br/>')

        ink = colors.HexColor('#172C41')
        muted = colors.HexColor('#526779')
        accent = colors.HexColor('#167D8D')
        body = ParagraphStyle('body', fontName='LessonRegular', fontSize=10, leading=14,
                              textColor=ink, spaceAfter=7, splitLongWords=True)
        title = ParagraphStyle('title', parent=body, fontName='LessonBold', fontSize=25, leading=31, spaceAfter=12)
        meta = ParagraphStyle('meta', parent=body, fontSize=9.5, leading=14, textColor=muted, spaceAfter=5)
        heading = ParagraphStyle('section', parent=body, fontName='LessonBold', fontSize=13,
                                 leading=18, textColor=accent, spaceBefore=12, spaceAfter=6, keepWithNext=True)
        word_style = ParagraphStyle('word', parent=body, fontName='LessonBold', textColor=ink,
                                    backColor=colors.HexColor('#EDF5F6'), borderPadding=5,
                                    spaceBefore=7, spaceAfter=7, keepWithNext=True)
        example_style = ParagraphStyle('example', parent=body, leftIndent=10, textColor=muted)
        date = lesson.scheduled_at.astimezone(ZoneInfo(lesson.timezone))
        stream = BytesIO()
        document = SimpleDocTemplate(stream, pagesize=A4, leftMargin=48, rightMargin=48,
                                     topMargin=48, bottomMargin=52, title='Матеріали уроку', author='AI English Tutor')
        story = [Paragraph('МАТЕРІАЛИ УРОКУ', meta), Paragraph('Англійська мова', title),
                 Paragraph(safe(f'{date:%d.%m.%Y}  |  {date:%H:%M}  |  {lesson.timezone}'), meta)]
        if student_name:
            story.append(Paragraph(safe(f'Учень: {student_name}'), meta))
        if teacher_name:
            story.append(Paragraph(safe(f'Викладач: {teacher_name}'), meta))
        story += [Paragraph('Аналіз перевірено та підтверджено викладачем.', meta), Spacer(1, 8)]
        for number, (key, label) in enumerate(BLOCKS.items(), 1):
            story.append(Paragraph(safe(f'{number:02d}  {label}'), heading))
            rule = HRFlowable(width='100%', thickness=0.7, color=colors.HexColor('#C5DCE0'), spaceAfter=8)
            rule.keepWithNext = True
            story.append(rule)
            text = blocks[key].replace('\r\n', '\n')
            if key == 'vocabulary':
                # Separate clearly delimited entries, retaining the original punctuation.
                text = re.sub(r';[ \t]*(?=[A-Za-z][A-Za-z’\x27 -]{0,60}\s*[-–—:])', ';\n\n', text)
                for paragraph in text.split('\n\n'):
                    lines = paragraph.splitlines()
                    for i, line in enumerate(lines):
                        if not line.strip():
                            continue
                        term = re.match(r'^(?:[-•]\s*)?(?:\d+[.)]\s*)?[A-Za-z][A-Za-z’\x27 -]{0,60}\s*[-–—:]\s*\S', line)
                        style = word_style if term else example_style
                        # A final term with no example must not force a blank next page.
                        if term and (i == len(lines)-1 or re.match(r'^[A-Za-z].*?\s[-–—:]\s', lines[i+1])):
                            style = ParagraphStyle('standalone-word', parent=word_style, keepWithNext=False)
                        story.append(Paragraph(safe(line), style))
                    story.append(Spacer(1, 3))
            else:
                # Numbered mistakes and tasks remain distinct even when pasted on one line.
                text = re.sub(r'(?<=\S)[ \t]+(?=\d+[.)]\s)', '\n\n', text)
                for paragraph in text.split('\n\n'):
                    if paragraph:
                        story.append(Paragraph(safe(paragraph), body))

        def footer(canvas, doc):
            canvas.saveState()
            canvas.setFillColor(accent)
            canvas.rect(48, A4[1] - 27, 42, 3, fill=1, stroke=0)
            canvas.setStrokeColor(colors.HexColor('#DCE5EB'))
            canvas.line(48, 39, A4[0] - 48, 39)
            canvas.setFont('LessonRegular', 8)
            canvas.setFillColor(muted)
            canvas.drawString(48, 25, f'AI English Tutor  |  {date:%d.%m.%Y}')
            canvas.drawRightString(A4[0] - 48, 25, f'Сторінка {doc.page}')
            canvas.restoreState()

        document.build(story, onFirstPage=footer, onLaterPages=footer)
        return stream.getvalue()
    except Exception:
        raise PdfGenerationError('pdf_generation_failed') from None
