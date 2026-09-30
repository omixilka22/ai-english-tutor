"""Poll the durable outbox. Never send real messages from tests."""
import asyncio
import logging
import math
from datetime import timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from app.bot.ui import keyboard
from app.database.database import AsyncSessionLocal
from app.database.models import Lesson, LessonNotification, Student, User, Teacher
from app.services.notification_service import schedule_reminders, invalid_reason, utcnow, OFFSETS, TEACHER_OFFSETS, MAX_ATTEMPTS

from app.services.meeting_service import meeting_url
from aiogram.types import InlineKeyboardButton

logger=logging.getLogger(__name__)
POLL_SECONDS=30
SEND_TIMEOUT=20


def notification_content(job,lesson,now,student=None,student_name=None):
    start=lesson.scheduled_at.astimezone(ZoneInfo(lesson.timezone))
    end=(lesson.scheduled_at+timedelta(minutes=lesson.duration_minutes)).astimezone(ZoneInfo(lesson.timezone))
    titles={'moved':'📅 Заняття перенесено','cancelled':'Заняття скасовано',
            'restored':'✓ Заняття відновлено','updated':'📅 Заняття оновлено','deleted':'Заняття видалено'}
    if job.kind in {*OFFSETS,*TEACHER_OFFSETS}:
        minutes=max(1,math.ceil((lesson.scheduled_at-now).total_seconds()/60))
        hours,minutes=divmod(minutes,60)
        remaining=(f'{hours} год ' if hours else '')+(f'{minutes} хв' if minutes else '')
        title=f'🔔 Заняття через {remaining.strip()}'
    else:
        title=titles[job.kind]
    text=f'{title}\n\n{start:%d.%m.%Y} · {start:%H:%M}–{end:%H:%M}\n{lesson.timezone}\nТривалість: {lesson.duration_minutes} хв'
    button=('📚 Мої заняття','notification_list') if lesson.is_deleted else ('📚 Відкрити заняття',f'notification_lesson_{lesson.id}')
    if job.kind in TEACHER_OFFSETS:
        text+='\nУчень: '+(student_name or 'Учень')
    markup=keyboard([[button]])
    if job.kind in ('reminder_1h','teacher_link_15m'):
        url=meeting_url(student)
        if url:
            markup.inline_keyboard.insert(0,[InlineKeyboardButton(text='🎥 Приєднатися до уроку',url=url)])
        else:
            text+='\n\nПосилання на урок ще не додано.'
            if job.kind=='teacher_link_15m':
                markup.inline_keyboard.insert(0,[InlineKeyboardButton(text='＋ Додати посилання',callback_data=f'notification_meet_{lesson.student_id}')])
    return text,markup


def record_failure(job,error,now):
    job.last_error=type(error).__name__  # Do not persist tokens or arbitrary exception text.
    if isinstance(error,(TelegramForbiddenError,TelegramBadRequest)):
        job.status='failed'
        return 0
    delay=max(1,int(error.retry_after)) if isinstance(error,TelegramRetryAfter) else min(30*2**(job.attempts-1),300)
    next_time=now+timedelta(seconds=delay)
    if job.attempts>=MAX_ATTEMPTS or next_time>job.expires_at:
        job.status='failed'
    else:
        job.next_attempt_at=next_time
    return delay if isinstance(error,TelegramRetryAfter) else 0


async def deliver_one(bot,job_id):
    """Locks are held through bounded Telegram I/O: parallel workers cannot double-send.

    A crash after Telegram accepts but before DB commit can still cause a duplicate.
    All writers lock lessons before outbox rows to avoid lock-order deadlocks.
    """
    async with AsyncSessionLocal() as session:
        reference=await session.get(LessonNotification,job_id)
        if reference is None:
            return 0
        lesson=(await session.execute(select(Lesson).where(Lesson.id==reference.lesson_id)
            .with_for_update())).scalar_one_or_none()
        job=(await session.execute(select(LessonNotification).where(LessonNotification.id==job_id)
            .with_for_update(skip_locked=True).execution_options(populate_existing=True))).scalar_one_or_none()
        now=utcnow()
        if job is None or job.status!='pending' or job.next_attempt_at>now:
            return 0
        student=(await session.execute(select(Student).where(Student.id==job.student_id)
            .with_for_update())).scalar_one_or_none()
        user=await session.get(User,student.user_id) if student else None
        student_name=user.name if user and job.kind in TEACHER_OFFSETS else None
        teacher=None
        if job.kind in TEACHER_OFFSETS:
            teacher=await session.get(Teacher,lesson.teacher_id) if lesson else None
            user=await session.get(User,teacher.user_id) if teacher else None
        reason=invalid_reason(job,lesson,student,user,now,teacher=teacher)
        if reason:
            job.status='skipped'
            job.last_error=reason
            await session.commit()
            return 0
        text,markup=notification_content(job,lesson,now,student,student_name)
        job.attempts+=1
        throttle=0
        try:
            sent=await asyncio.wait_for(bot.send_message(chat_id=user.telegram_id,text=text,reply_markup=markup),timeout=SEND_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            throttle=record_failure(job,error,utcnow())
            logger.warning('Notification %s attempt %s failed: %s',job.id,job.attempts,type(error).__name__)
        else:
            job.status='sent'
            job.sent_at=utcnow()
            job.telegram_message_id=sent.message_id
            job.last_error=None
        await session.commit()
        return throttle


async def tick(bot):
    async with AsyncSessionLocal() as session:
        await schedule_reminders(session)
        ids=(await session.execute(select(LessonNotification.id).where(
            LessonNotification.status=='pending',LessonNotification.next_attempt_at<=utcnow()
        ).order_by(LessonNotification.next_attempt_at,LessonNotification.id).limit(100))).scalars().all()
    for job_id in ids:
        try:
            throttle=await deliver_one(bot,job_id)
            if throttle:
                return throttle
        except Exception:
            logger.exception('Notification delivery failed for job %s',job_id)
        await asyncio.sleep(0.05)
    return 0


async def run(bot):
    while True:
        pause=POLL_SECONDS
        try:
            pause=max(pause,await tick(bot))
        except Exception:
            logger.exception('Notification worker unavailable; retrying')
        await asyncio.sleep(pause)
