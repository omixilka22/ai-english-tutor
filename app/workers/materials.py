"""Durable analysis and approved delivery; Telegram is at-least-once on crashes."""
import asyncio
import logging
from datetime import timedelta
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile
from sqlalchemy import select, or_, and_
from app.database.database import AsyncSessionLocal
from app.database.models import (Lesson, LessonStatus, LessonAnalysis, AnalysisStatus, Transcript,
                                 Teacher, Student, User, UserRole)
from app.services import gemini_analysis
from app.services.material_notices import publish_notice
from app.services.lesson_pdf import build_lesson_pdf, PdfGenerationError
from app.services.calendar_service import utcnow
from app.bot.ui import keyboard

logger = logging.getLogger(__name__)


async def participants(session, lesson):
    student = (await session.execute(select(Student).where(Student.id == lesson.student_id)
                                    .with_for_update())).scalar_one_or_none()
    teacher = await session.get(Teacher, lesson.teacher_id)
    su = await session.get(User, student.user_id) if student else None
    tu = await session.get(User, teacher.user_id) if teacher else None
    if (student is None or student.teacher_id != lesson.teacher_id or su is None or tu is None
            or su.role != UserRole.STUDENT or tu.role != UserRole.TEACHER):
        raise ValueError('recipient_unavailable')
    return su, tu


async def process_one(bot, lesson_id):
    # Lesson lock prevents stale approvals, concurrent edits and duplicate sends.
    # No schedule locks are acquired here. External calls have bounded timeouts.
    async with AsyncSessionLocal() as session:
        lesson = (await session.execute(select(Lesson).where(Lesson.id == lesson_id)
                                       .with_for_update(skip_locked=True))).scalar_one_or_none()
        if lesson is None or not getattr(lesson, 'conducted_at', None):
            return
        analysis = (await session.execute(select(LessonAnalysis).where(
            LessonAnalysis.lesson_id == lesson_id))).scalar_one_or_none()
        if analysis is None or analysis.workflow_state not in ('queued', 'approved', 'review', 'failed'):
            return
        if analysis.next_attempt_at and analysis.next_attempt_at > utcnow():
            return
        if analysis.workflow_state in ('review', 'failed') and analysis.review_notified:
            return
        if lesson.is_deleted or lesson.status == LessonStatus.CANCELLED:
            analysis.workflow_state = 'blocked'
            analysis.last_error = 'lesson_inactive'
            await session.commit()
            return
        try:
            student, teacher = await participants(session, lesson)
        except ValueError:
            analysis.workflow_state = 'blocked'
            analysis.last_error = 'recipient_unavailable'
            await session.commit()
            return
        if analysis.workflow_state == 'queued':
            analysis.attempts += 1
            transcript = (await session.execute(select(Transcript).where(
                Transcript.lesson_id == lesson_id))).scalar_one_or_none()
            try:
                if transcript is None:
                    raise gemini_analysis.AnalysisError('missing_transcript')
                analysis.content = await asyncio.wait_for(gemini_analysis.analyze(transcript.text), timeout=95)
            except (gemini_analysis.AnalysisError, TimeoutError) as error:
                code = error.code if isinstance(error, gemini_analysis.AnalysisError) else 'network'
                analysis.last_error = code
                if code in {'http_500', 'http_502', 'http_503', 'http_504'} and analysis.attempts < 3:
                    analysis.next_attempt_at = utcnow() + timedelta(seconds=30 * 2 ** (analysis.attempts - 1))
                else:
                    analysis.workflow_state = 'failed'
                    analysis.next_attempt_at = None
                    analysis.attempts = 0
                logger.warning('Gemini lesson %s failed: %s', lesson_id, code)
            else:
                analysis.attempts = 0
                analysis.workflow_state = 'review'
                analysis.status = AnalysisStatus.READY_FOR_REVIEW
                analysis.revision += 1
                analysis.last_error = None
                analysis.next_attempt_at = None
            await session.commit()
            return
        if analysis.workflow_state in ('review', 'failed'):
            try:
                await asyncio.wait_for(publish_notice(session, bot, teacher,
                    text=('✓ Аналіз уроку готовий. Перевірте чотири блоки перед надсиланням учню.'
                          if analysis.workflow_state == 'review' else
                          'Аналіз не виконано. Транскрипт збережено. Відкрийте матеріали, щоб побачити причину й повторити.'),
                    markup=keyboard([[('Перевірити аналіз', f'notification_material_{lesson_id}')]])), timeout=20)
            except Exception as error:
                # Review remains available in the menu even if the notice cannot be delivered.
                analysis.attempts += 1
                delay = max(30, error.retry_after) if isinstance(error, TelegramRetryAfter) else 60
                analysis.next_attempt_at = utcnow() + timedelta(seconds=delay)
                if analysis.attempts >= 5 or isinstance(error, (TelegramForbiddenError, TelegramBadRequest)):
                    analysis.review_notified = True
            else:
                analysis.review_notified = True
                analysis.attempts = 0
                analysis.next_attempt_at = None
            await session.commit()
            return
        # Only a persisted teacher approval enters this branch. One document avoids partial sends.
        analysis.attempts += 1
        try:
            pdf = await asyncio.to_thread(build_lesson_pdf, lesson, analysis.content,
                                          student_name=getattr(student, 'name', ''),
                                          teacher_name=getattr(teacher, 'name', ''))
        except PdfGenerationError as error:
            analysis.last_error = str(error)
            analysis.workflow_state = 'send_failed'
            await session.commit()
            return
        try:
            sent = await asyncio.wait_for(bot.send_document(chat_id=student.telegram_id,
                document=BufferedInputFile(pdf, filename=f'lesson_{lesson_id}.pdf'),
                caption='📚 Повний PDF із матеріалами уроку, перевіреними викладачем. Їх також можна прочитати в боті.',
                reply_markup=keyboard([[('Відкрити матеріали', f'notification_material_{lesson_id}')]])), timeout=30)
        except Exception as error:
            analysis.last_error = 'delivery_failed'
            if analysis.attempts >= 5 or isinstance(error, (TelegramForbiddenError, TelegramBadRequest, ValueError)):
                analysis.workflow_state = 'send_failed'
            else:
                delay = max(1, error.retry_after) if isinstance(error, TelegramRetryAfter) else 30 * 2 ** (analysis.attempts - 1)
                analysis.next_attempt_at = utcnow() + timedelta(seconds=delay)
        else:
            analysis.workflow_state = 'sent'
            analysis.telegram_message_id = sent.message_id
            analysis.last_error = None
            analysis.next_attempt_at = None
        await session.commit()


async def tick(bot):
    async with AsyncSessionLocal() as session:
        ids = (await session.execute(select(LessonAnalysis.lesson_id).join(Lesson, Lesson.id == LessonAnalysis.lesson_id).where(
            Lesson.conducted_at.is_not(None),
            or_(LessonAnalysis.workflow_state.in_(('queued', 'approved')),
                and_(LessonAnalysis.workflow_state.in_(('review', 'failed')), LessonAnalysis.review_notified.is_(False))),
            or_(LessonAnalysis.next_attempt_at.is_(None), LessonAnalysis.next_attempt_at <= utcnow())
        ).order_by(LessonAnalysis.id).limit(20))).scalars().all()
    for lesson_id in ids:
        try:
            await process_one(bot, lesson_id)
        except Exception as error:
            logger.warning('Material job %s failed: %s', lesson_id, type(error).__name__)


async def run(bot):
    while True:
        try:
            await tick(bot)
        except Exception as error:
            logger.warning('Material worker unavailable: %s', type(error).__name__)
        await asyncio.sleep(10)
