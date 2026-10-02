"""Authorized transitions; all writers serialize through the lesson lock."""
from datetime import timedelta
from sqlalchemy import select
from app.database.models import Lesson, LessonStatus, Transcript, LessonAnalysis, AnalysisStatus
from app.services.calendar_service import CalendarService, utcnow
from app.services.analysis_content import validate_transcript, validate_content, BLOCKS


def require_conducted(lesson):
    if not getattr(lesson, 'conducted_at', None) or lesson.status == LessonStatus.CANCELLED:
        raise ValueError('Спочатку підтвердьте, що урок проведено.')


async def confirm_attendance(session, telegram_id, lesson_id, *, conducted=True):
    lesson, _ = await CalendarService.lesson_access(session, telegram_id, lesson_id, write=True)
    if lesson.status == LessonStatus.CANCELLED:
        raise ValueError('Заняття скасоване.')
    if lesson.scheduled_at + timedelta(minutes=lesson.duration_minutes) > utcnow():
        raise ValueError('Позначити результат можна після завершення запланованого часу уроку.')
    if getattr(lesson, 'conducted_at', None):
        if conducted:
            return
        raise ValueError('Проведення цього уроку вже підтверджено.')
    analysis = await analysis_for(session, lesson_id)
    if conducted:
        lesson.conducted_at = utcnow()
        lesson.conducted_by = lesson.teacher_id
        lesson.status = LessonStatus.COMPLETED
    else:
        if analysis and analysis.workflow_state in ('approved', 'send_failed', 'sent'):
            raise ValueError('Матеріали вже підтверджені або надіслані. Не можна позначити урок як непроведений.')
        lesson.status = LessonStatus.CANCELLED
        lesson.is_exception = True
        lesson.notification_version += 1
        if analysis:
            analysis.workflow_state = 'blocked'
            analysis.last_error = 'lesson_inactive'
    await session.commit()


async def analysis_for(session, lesson_id):
    return (await session.execute(select(LessonAnalysis).where(
        LessonAnalysis.lesson_id == lesson_id).execution_options(populate_existing=True))).scalar_one_or_none()


async def get_material(session, telegram_id, lesson_id, *, write=False):
    lesson, teacher = await CalendarService.lesson_access(session, telegram_id, lesson_id, write=write)
    analysis = await analysis_for(session, lesson_id)
    if not teacher:
        require_conducted(lesson)
    if not teacher and (analysis is None or analysis.workflow_state not in ('approved', 'send_failed', 'sent')):
        raise ValueError('Матеріали ще не підтверджені викладачем.')
    return lesson, teacher, analysis


async def list_materials(session, telegram_id, student_id=None):
    student, teacher = await CalendarService.student_access(session, telegram_id, student_id)
    statement = select(Lesson).where(Lesson.student_id == student.id, Lesson.is_deleted.is_(False))
    if teacher:
        statement = statement.where(Lesson.teacher_id == student.teacher_id, Lesson.scheduled_at <= utcnow(),
                                    Lesson.status != LessonStatus.CANCELLED)
    else:
        statement = statement.join(LessonAnalysis, LessonAnalysis.lesson_id == Lesson.id).where(
            Lesson.conducted_at.is_not(None),
            LessonAnalysis.workflow_state.in_(('approved', 'send_failed', 'sent')))
    lessons = (await session.execute(statement.order_by(Lesson.scheduled_at.desc()).limit(100))).scalars().all()
    return student, teacher, lessons


async def upload(session, telegram_id, lesson_id, text):
    text = validate_transcript(text)
    lesson, _, existing = await get_material(session, telegram_id, lesson_id, write=True)
    require_conducted(lesson)
    if lesson.status == LessonStatus.CANCELLED or lesson.scheduled_at + timedelta(minutes=lesson.duration_minutes) > utcnow():
        raise ValueError('Додати транскрипт можна після завершення часу заняття.')
    transcript = (await session.execute(select(Transcript).where(Transcript.lesson_id == lesson_id))).scalar_one_or_none()
    if existing is not None or transcript is not None:
        raise ValueError('Транскрипт або аналіз уже існує. Відкрийте матеріали заняття.')
    session.add(Transcript(lesson_id=lesson_id, text=text, source='manual'))
    session.add(LessonAnalysis(lesson_id=lesson_id, content={}, status=AnalysisStatus.PROCESSING,
                              workflow_state='queued', revision=1, attempts=0, review_notified=False))
    await session.commit()


def check_revision(analysis, revision, allowed):
    if analysis is None or analysis.revision != revision or analysis.workflow_state not in allowed:
        raise ValueError('Матеріали вже змінилися. Відкрийте їх знову.')


async def edit_block(session, telegram_id, lesson_id, revision, key, text):
    lesson, _, analysis = await get_material(session, telegram_id, lesson_id, write=True)
    require_conducted(lesson)
    check_revision(analysis, revision, {'review'})
    if key not in BLOCKS:
        raise ValueError('Невідомий блок.')
    analysis.content = validate_content({**analysis.content, key: text})
    analysis.revision += 1
    await session.commit()


async def approve(session, telegram_id, lesson_id, revision):
    lesson, _, analysis = await get_material(session, telegram_id, lesson_id, write=True)
    require_conducted(lesson)
    check_revision(analysis, revision, {'review'})
    analysis.content = validate_content(analysis.content)
    analysis.status = AnalysisStatus.APPROVED
    analysis.workflow_state = 'approved'
    analysis.revision += 1
    analysis.attempts = 0
    analysis.last_error = None
    analysis.next_attempt_at = utcnow()
    await session.commit()


async def retry(session, telegram_id, lesson_id, revision):
    lesson, _, analysis = await get_material(session, telegram_id, lesson_id, write=True)
    require_conducted(lesson)
    check_revision(analysis, revision, {'failed', 'send_failed'})
    if analysis.workflow_state == 'failed':
        analysis.review_notified = False
    analysis.workflow_state = 'queued' if analysis.workflow_state == 'failed' else 'approved'
    analysis.status = AnalysisStatus.PROCESSING if analysis.workflow_state == 'queued' else AnalysisStatus.APPROVED
    analysis.revision += 1
    analysis.last_error = None
    analysis.attempts = 0
    analysis.next_attempt_at = utcnow()
    await session.commit()
