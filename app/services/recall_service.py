"""Teacher-authorized manual capture for one concrete lesson."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from app.config import settings
from app.database.models import RecallSession, LessonStatus, Student, Teacher, Transcript, LessonAnalysis
from app.services.calendar_service import CalendarService, utcnow
from app.services.meeting_service import meeting_url, normalize_meeting_url
from app.services import recall_client as client


async def session_for(db, lesson_id):
    return (await db.execute(select(RecallSession).where(RecallSession.lesson_id==lesson_id))).scalar_one_or_none()


async def start(db, telegram_id, lesson_id):
    lesson,_=await CalendarService.lesson_access(db,telegram_id,lesson_id,write=True)
    existing=await session_for(db,lesson_id)
    if existing:
        # Only definitive Create Bot rejections are safe to retry with no provider object.
        if existing.state=='failed' and not existing.bot_id and existing.error in ('http_400','http_401','http_403','http_429','http_507','not_configured'):
            now=utcnow()
            if lesson.status!=LessonStatus.SCHEDULED or not lesson.scheduled_at-timedelta(minutes=15)<=now<lesson.scheduled_at+timedelta(minutes=lesson.duration_minutes):
                raise ValueError('Урок уже не в межах часу запуску.')
            existing.state='queued';existing.error=None;existing.attempts=0
            existing.next_attempt_at=None;existing.notice_sent=False
            await db.commit()
        return existing
    if not client.configured() or not settings.RECALL_WEBHOOK_SECRET or not settings.RECALL_WEBHOOK_READY:
        raise ValueError('Спочатку налаштуйте ключ Recall, підпис вебхуків і HTTPS-тунель. Дивіться docs/recall-setup.md.')
    now=utcnow()
    end=lesson.scheduled_at+timedelta(minutes=lesson.duration_minutes)
    if lesson.status!=LessonStatus.SCHEDULED or lesson.conducted_at or not lesson.scheduled_at-timedelta(minutes=15)<=now<end:
        raise ValueError('Запуск доступний за 15 хв до уроку та під час його запланованого часу.')
    if (await db.execute(select(Transcript.id).where(Transcript.lesson_id==lesson_id))).scalar_one_or_none() is not None:
        raise ValueError('Для уроку вже є транскрипт.')
    if (await db.execute(select(LessonAnalysis.id).where(LessonAnalysis.lesson_id==lesson_id))).scalar_one_or_none() is not None:
        raise ValueError('Для уроку вже є аналіз.')
    student=await db.get(Student,lesson.student_id)
    url=meeting_url(student)
    if not url: raise ValueError('Спочатку додайте посилання Google Meet у картці учня.')
    url=normalize_meeting_url(url)
    await db.execute(select(Teacher).where(Teacher.id==lesson.teacher_id).with_for_update())
    active=(await db.execute(select(RecallSession.id).where(RecallSession.meeting_url==url,
        RecallSession.state.in_(['queued','creating','create_unknown','joining','recording']),
        RecallSession.leave_sent.is_(False)))).scalar_one_or_none()
    if active: raise ValueError('До цієї кімнати вже підключається помічник іншого уроку.')
    row=RecallSession(id=str(uuid4()),lesson_id=lesson_id,meeting_url=url,state='queued',
        created_at=now,expires_at=now+timedelta(days=7),stop_at=end+timedelta(minutes=15),
        attempts=0,cleanup_state='none',notice_sent=False,leave_requested=False,leave_sent=False)
    db.add(row)
    await db.commit()
    return row


async def stop(db,telegram_id,lesson_id):
    await CalendarService.lesson_access(db,telegram_id,lesson_id,write=True)
    row=await session_for(db,lesson_id)
    if row:
        row.leave_requested=True
        if row.state=='queued': row.state='cancelled'
        await db.commit()
    return row
