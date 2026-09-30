"""Manual reusable Google Meet links, scoped to the current teacher."""
import re
from sqlalchemy import select
from app.database.models import Student
from app.services.calendar_service import CalendarService


def normalize_meeting_url(raw):
    value=raw.strip()
    if not re.fullmatch(r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}',value):
        raise ValueError('Вставте посилання виду https://meet.google.com/abc-defg-hij без додаткового тексту.')
    return value


def meeting_url(student):
    if student and getattr(student,'meeting_teacher_id',None)==student.teacher_id:
        return getattr(student,'meeting_url',None)
    return None


async def save_meeting_url(session,telegram_id,student_id,value):
    value=normalize_meeting_url(value) if value is not None else None
    student,_=await CalendarService.student_access(session,telegram_id,student_id,write=True)
    owner=student.teacher_id
    student=(await session.execute(select(Student).where(Student.id==student_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if student is None or student.teacher_id!=owner:
        raise ValueError('Учень більше не належить цьому викладачу.')
    student.meeting_url=value
    student.meeting_teacher_id=owner if value else None
    await session.commit()
