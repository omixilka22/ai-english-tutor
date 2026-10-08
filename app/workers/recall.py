"""Webhook-driven async transcription; persisted intents prevent blind paid retries."""
import asyncio
import logging
from datetime import timedelta
from sqlalchemy import select, delete, or_
from app.database.database import AsyncSessionLocal
from app.database.models import (RecallSession,RecallEvent,Lesson,LessonStatus,Transcript,
    LessonAnalysis,AnalysisStatus,Student,Teacher,User)
from app.services.calendar_service import utcnow
from app.services import recall_client as client
from app.services.material_notices import publish_notice
from app.bot.ui import keyboard

logger=logging.getLogger(__name__)


async def consume_events():
    async with AsyncSessionLocal() as db:
        events=(await db.execute(select(RecallEvent).where(RecallEvent.done.is_(False))
            .order_by(RecallEvent.created_at).limit(100).with_for_update(skip_locked=True))).scalars().all()
        for event in events:
            row=(await db.execute(select(RecallSession).where(RecallSession.bot_id==event.bot_id)
                .with_for_update())).scalar_one_or_none()
            if row is None and event.session_id:
                row=await db.get(RecallSession,event.session_id,with_for_update=True)
                if row and row.bot_id not in (None,event.bot_id): row=None
            if row is None:
                event.done=True
                continue
            row.bot_id=event.bot_id
            if event.recording_id:
                if row.recording_id not in (None,event.recording_id):
                    row.error='multiple_recordings';event.done=True;continue
                row.recording_id=event.recording_id
            if event.event in ('recording.done','bot.done','bot.call_ended'):
                row.leave_sent=True
            if row.cleanup_state!='none':
                if event.recording_id or event.transcript_id:
                    row.cleanup_state='pending';row.state='cleanup';row.next_attempt_at=None
                    if event.transcript_id: row.transcript_id=event.transcript_id
                event.done=True;continue
            if event.event=='recording.done' and row.state in ('queued','creating','create_unknown','joining','recording','ended','failed'):
                row.state='recorded';row.error=None;row.next_attempt_at=None
            elif event.event=='transcript.done' and event.transcript_id and event.recording_id==row.recording_id:
                if row.transcript_id not in (None,event.transcript_id):
                    event.done=True;continue
                if row.state not in ('ready_roles','ready','analysis','cleaned'):
                    row.transcript_id=event.transcript_id;row.state='download';row.error=None;row.next_attempt_at=None
            elif event.event=='transcript.failed' and row.state in ('transcribing','transcribe_unknown'):
                row.state='failed';row.error='transcription_failed'
            elif event.event in ('bot.fatal','recording.failed') and row.state in ('queued','creating','create_unknown','joining','recording','ended'):
                row.state='failed';row.error='meeting_failed'
            elif event.event=='bot.in_call_recording' and row.state in ('queued','creating','create_unknown','joining'):
                row.state='recording'
            elif event.event in ('bot.call_ended','bot.done') and row.state in ('queued','creating','create_unknown','joining','recording'):
                row.state='ended';row.leave_sent=True
            elif event.event in ('bot.joining_call','bot.in_waiting_room') and row.state in ('queued','creating','create_unknown'):
                row.state='joining'
            event.done=True
        await db.commit()


async def notify(db,bot,row,lesson,text):
    if row.notice_sent: return
    teacher=await db.get(Teacher,lesson.teacher_id)
    user=await db.get(User,teacher.user_id) if teacher else None
    if user:
        await publish_notice(db,bot,user,text,keyboard([[('Відкрити транскрибацію',f'recall_{lesson.id}')]]))
        row.notice_sent=True


async def process_one(bot, session_id):
    async with AsyncSessionLocal() as db:
        # Same lock order as attendance/material worker: lesson, then capture.
        probe=await db.get(RecallSession,session_id)
        if not probe: return
        lesson=(await db.execute(select(Lesson).where(Lesson.id==probe.lesson_id)
            .with_for_update(skip_locked=True))).scalar_one_or_none()
        if not lesson: return
        row=(await db.execute(select(RecallSession).where(RecallSession.id==session_id)
            .with_for_update(skip_locked=True).execution_options(populate_existing=True))).scalar_one_or_none()
        if not row: return
        now=utcnow()
        if row.next_attempt_at and row.next_attempt_at>now: return
        analysis=(await db.execute(select(LessonAnalysis).where(LessonAnalysis.lesson_id==lesson.id))).scalar_one_or_none()
        student=await db.get(Student,lesson.student_id)
        inactive=lesson.is_deleted or lesson.status==LessonStatus.CANCELLED or not student or student.teacher_id!=lesson.teacher_id
        delivered=bool(analysis and analysis.workflow_state=='sent')
        expired=now>=row.expires_at
        if inactive or delivered or expired:
            await db.execute(delete(Transcript).where(Transcript.lesson_id==lesson.id,Transcript.source.in_(['recall','recall_unverified'])))
            row.meeting_url=None
            if not delivered and analysis and analysis.workflow_state in ('queued','review','failed'):
                analysis.workflow_state='blocked';analysis.last_error='transcript_expired' if expired else 'lesson_inactive'
            if row.cleanup_state=='none': row.cleanup_state='pending'
            if row.state=='queued': row.state='cancelled'
            row.leave_requested=True
            await db.commit()  # Local erasure must survive an unavailable remote leave endpoint.
        if row.bot_id and not row.leave_sent and (row.leave_requested or now>=row.stop_at):
            try:
                await client.request('POST',f'/api/v1/bot/{client.identifier(row.bot_id)}/leave_call/')
            except client.RecallError as error:
                if error.code=='http_400':
                    info=await client.request('GET',f'/api/v1/bot/{client.identifier(row.bot_id)}/')
                    codes=[s.get('code') for s in info.get('status_changes',[])]
                    if not codes or codes[-1] not in ('done','fatal','call_ended'): raise
                elif error.code!='http_404': raise
            row.leave_sent=True
        if row.cleanup_state=='pending':
            # Persist local erasure before making any remote calls.
            await db.commit()
            if row.transcript_id:
                await client.request('DELETE',f'/api/v1/transcript/{client.identifier(row.transcript_id)}/')
            if row.recording_id:
                await client.request('DELETE',f'/api/v1/recording/{client.identifier(row.recording_id)}/')
                row.cleanup_state='done';row.state='cleaned'
            elif row.bot_id and row.leave_sent:
                await client.request('POST',f'/api/v1/bot/{client.identifier(row.bot_id)}/delete_media/')
                row.cleanup_state='done';row.state='cleaned'
            elif not row.bot_id and row.state in ('cancelled','failed'):
                row.cleanup_state='done';row.state='cleaned'
            # Wait for recording.done to learn its ID if the call has only just ended.
            row.next_attempt_at=now+timedelta(minutes=5)
            await db.commit();return
        if row.state=='queued':
            if now>=lesson.scheduled_at+timedelta(minutes=lesson.duration_minutes):
                row.state='failed';row.error='missed_start';row.notice_sent=False
                await db.commit();return
            row.state='creating';row.attempts+=1
            await db.commit()  # An interrupted/ambiguous POST must never be blindly repeated.
            try:
                data=await client.request('POST','/api/v1/bot/',client.bot_payload(row))
                row.bot_id=client.identifier(data['id']);row.state='joining';row.error=None
            except client.RecallError as error:
                row.error=error.code
                if error.code=='http_507' and row.attempts<10:
                    row.state='queued';row.next_attempt_at=now+timedelta(seconds=30)
                else:
                    row.state='create_unknown' if error.code=='network_unknown' or error.code.startswith('http_5') else 'failed'
            except (KeyError,TypeError):
                row.state='create_unknown';row.error='invalid_response'
            await db.commit();return
        if row.state=='recorded':
            row.state='transcribing'
            await db.commit()
            try:
                data=await client.request('POST',f'/api/v1/recording/{client.identifier(row.recording_id)}/create_transcript/',
                    {'provider':{'recallai_async':{'language_code':'auto'}},
                     'diarization':{'use_separate_streams_when_available':True}})
                row.transcript_id=client.identifier(data['id'])
            except client.RecallError as error:
                row.state='transcribe_unknown' if error.code=='network_unknown' or error.code.startswith('http_5') else 'failed'
                row.error=error.code
            except (KeyError,TypeError):
                row.state='transcribe_unknown';row.error='invalid_response'
            await db.commit();return
        if row.state=='download':
            data=await client.request('GET',f'/api/v1/transcript/{client.identifier(row.transcript_id)}/')
            try: url=data['data']['download_url']
            except (TypeError,KeyError): raise client.RecallError('missing_download') from None
            text=client.transcript_text(await client.download(url))
            existing=(await db.execute(select(Transcript).where(Transcript.lesson_id==lesson.id))).scalar_one_or_none()
            if existing or analysis:
                row.state='failed';row.error='material_exists'
            else:
                db.add(Transcript(lesson_id=lesson.id,text=text,source='recall_unverified'))
                row.state='ready_roles';row.error=None;row.notice_sent=False
            await db.commit();return
        if row.state=='ready_roles':
            await notify(db,bot,row,lesson,'✓ Текст уроку отримано. Перевірте, хто з учасників є викладачем, перед аналізом.')
        elif row.state=='ready' and lesson.conducted_at:
            if not analysis:
                db.add(LessonAnalysis(lesson_id=lesson.id,content={},status=AnalysisStatus.PROCESSING,
                    workflow_state='queued',revision=1,attempts=0,review_notified=False))
            row.state='analysis'
        elif row.state in ('failed','create_unknown','transcribe_unknown'):
            await notify(db,bot,row,lesson,'Не вдалося завершити транскрибацію. Відкрийте її стан у картці уроку.')
        if not delivered and now>=row.expires_at-timedelta(days=1) and not row.cleanup_after:
            row.notice_sent=False
            await notify(db,bot,row,lesson,'Термін зберігання транскрипту завершується протягом доби. Завершіть перевірку й надсилання матеріалів.')
            row.cleanup_after=now
        row.next_attempt_at=now+timedelta(seconds=60)
        await db.commit()


async def tick(bot):
    await consume_events()
    async with AsyncSessionLocal() as db:
        ids=(await db.execute(select(RecallSession.id).where(RecallSession.state!='cleaned',
            or_(RecallSession.next_attempt_at.is_(None),RecallSession.next_attempt_at<=utcnow()))
            .order_by(RecallSession.created_at).limit(50))).scalars().all()
    for session_id in ids:
        try:
            await process_one(bot,session_id)
        except Exception as error:
            code=error.code if isinstance(error,client.RecallError) else 'internal_error'
            logger.warning('Recall job %s: %s',session_id,code)
            async with AsyncSessionLocal() as db:
                row=await db.get(RecallSession,session_id,with_for_update=True)
                if row:
                    row.error=code;row.next_attempt_at=utcnow()+timedelta(minutes=2)
                    if row.state=='download' and code in ('invalid_transcript','empty_transcript','transcript_too_long','unsafe_download','response_too_large'):
                        row.state='failed';row.notice_sent=False
                    await db.commit()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RecallEvent).where(RecallEvent.done.is_(True),RecallEvent.created_at<utcnow()-timedelta(days=7)))
        await db.commit()


async def run(bot):
    while True:
        try: await tick(bot)
        except Exception as error: logger.warning('Recall worker unavailable: %s',type(error).__name__)
        await asyncio.sleep(10)
