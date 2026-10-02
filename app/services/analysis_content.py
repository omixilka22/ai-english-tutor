"""Validated, editable lesson material; transcript text is untrusted input."""
from io import BytesIO

BLOCKS = {'summary': 'Підсумок уроку', 'mistakes': 'Помилки та пояснення',
          'vocabulary': 'Нові слова', 'homework': 'Домашнє завдання'}
MAX_TRANSCRIPT_CHARS = 60000
MAX_FILE_BYTES = 256 * 1024
MAX_BLOCK_CHARS = 2800


def validate_transcript(text):
    text = text.strip()
    if not text or len(text) > MAX_TRANSCRIPT_CHARS or '\x00' in text:
        raise ValueError('Транскрипт має містити від 1 до 60 000 символів звичайного тексту.')
    return text


def validate_content(content):
    if not isinstance(content, dict) or set(content) != set(BLOCKS):
        raise ValueError('Аналіз має містити рівно чотири узгоджені блоки.')
    clean = {}
    for key in BLOCKS:
        value = content[key]
        if not isinstance(value, str) or not value.strip() or len(value.encode('utf-16-le')) // 2 > MAX_BLOCK_CHARS or '\x00' in value:
            raise ValueError('Кожен блок має містити від 1 до 2800 символів тексту.')
        clean[key] = value.strip()
    return clean


class LimitedBuffer(BytesIO):
    def write(self, data):
        if self.tell() + len(data) > MAX_FILE_BYTES:
            raise ValueError('Файл завеликий. Максимум — 256 КБ.')
        return super().write(data)


def decode_transcript(data):
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('Файл завеликий. Максимум — 256 КБ.')
    try:
        return validate_transcript(data.decode('utf-8-sig'))
    except UnicodeDecodeError:
        raise ValueError('Збережіть .txt-файл у кодуванні UTF-8.') from None


def material_text(lesson, content):
    from zoneinfo import ZoneInfo
    date = lesson.scheduled_at.astimezone(ZoneInfo(lesson.timezone))
    blocks = validate_content(content)
    return f'Матеріали уроку {date:%d.%m.%Y %H:%M} ({lesson.timezone})\n\n' + '\n\n'.join(
        f'{title}\n{blocks[key]}' for key, title in BLOCKS.items())
