import os
import unittest
import json
import time
import base64
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as Obj
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
for k,v in {'POSTGRES_DB':'test','POSTGRES_USER':'test','POSTGRES_PASSWORD':'test','TELEGRAM_BOT_TOKEN':'123456:TEST_TOKEN','TEACHER_REGISTRATION_CODE':'test'}.items():
    os.environ.setdefault(k,v)
from app.services import recall_client as client, recall_service as service
from app.workers import recall as worker
from app.bot.handlers.recall import assign_roles, speakers
from app.database.models import LessonStatus, Transcript, LessonAnalysis

NOW=datetime(2026,10,8,12,tzinfo=timezone.utc)
BOT=str(uuid4());SESSION=str(uuid4());RECORD=str(uuid4());TRANSCRIPT=str(uuid4())


def result(value=None,rows=None):
    r=MagicMock();r.scalar_one_or_none.return_value=value;r.scalars.return_value.all.return_value=rows or []
    return r


def capture(**kw):
    d=dict(id=SESSION,lesson_id=1,bot_id=BOT,recording_id=RECORD,transcript_id=TRANSCRIPT,
        meeting_url='https://meet.google.com/abc-defg-hij',state='ready',error=None,attempts=0,
        next_attempt_at=None,stop_at=NOW+timedelta(hours=1),created_at=NOW,
        expires_at=NOW+timedelta(days=7),cleanup_state='none',cleanup_after=None,
        leave_sent=False,leave_requested=False,notice_sent=False)
    d.update(kw);return Obj(**d)


def lesson(**kw):
    d=dict(id=1,student_id=2,teacher_id=3,scheduled_at=NOW,duration_minutes=60,
        status=LessonStatus.SCHEDULED,is_deleted=False,conducted_at=None)
    d.update(kw);return Obj(**d)


def signed(body,stamp=None):
    stamp=str(stamp or int(time.time()));key=b'test-signing-key'
    signature=base64.b64encode(hmac.new(key,b'event1.'+stamp.encode()+b'.'+body,hashlib.sha256).digest()).decode()
    return {'webhook-id':'event1','webhook-timestamp':stamp,'webhook-signature':'v1,'+signature},'whsec_'+base64.b64encode(key).decode()


class ClientTests(unittest.TestCase):
    def test_signature_exact_body_rotation_and_replay_window(self):
        body=b'{"event":"recording.done"}'
        headers,secret=signed(body)
        self.assertEqual(client.verify_signature(body,headers,secret),'event1')
        headers['webhook-signature']='v1,wrong '+headers['webhook-signature']
        self.assertEqual(client.verify_signature(body,headers,secret),'event1')
        for data,head in [(body+b' ',headers),(body,signed(body,int(time.time())-301)[0]),(body,{})]:
            with self.assertRaises(client.RecallError): client.verify_signature(data,head,secret)

    def test_ids_cannot_inject_api_path(self):
        for value in ['../bot/',None,'abc']:
            with self.assertRaises(client.RecallError):client.identifier(value)

    def test_mixed_transcript_preserves_grammar_and_languages(self):
        payload=[{'participant':{'id':1,'name':'Anna'},'words':[
            {'text':'Yesterday I go. А як сказати магазин?','start_timestamp':{'relative':12}}]}]
        text=client.transcript_text(payload)
        self.assertIn('Yesterday I go.',text);self.assertIn('А як сказати магазин?',text)
        self.assertNotIn('Student:',text)
        self.assertIn('[00:12]',text)

    def test_empty_invalid_and_oversized_rejected_without_truncation(self):
        for payload in [[],{},[{'words':[{}]}],[{'words':[{'text':'a'*200001,'start_timestamp':{'relative':0}}]}]]:
            with self.assertRaises(client.RecallError):client.transcript_text(payload)

    def test_two_speakers_need_explicit_teacher_assignment(self):
        text='[00:01] Учасник 1 (Anna): Hello\n[00:02] Учасник 2 (Tutor): Привіт'
        self.assertEqual(len(speakers(text)),2)
        assigned=assign_roles(text,'2')
        self.assertIn('Teacher: Привіт',assigned);self.assertIn('Student: Hello',assigned)
        with self.assertRaises(ValueError):assign_roles(text,'99')

    def test_bot_has_budget_limits_and_no_video(self):
        payload=client.bot_payload(capture())
        self.assertGreaterEqual(payload['automatic_leave']['everyone_left_timeout']['activate_after'],1)
        self.assertIsNone(payload['recording_config']['video_mixed_mp4'])
        self.assertEqual(payload['automatic_leave']['everyone_left_timeout']['timeout'],60)
        self.assertEqual(payload['automatic_leave']['in_call_recording_timeout'],3600)
        self.assertEqual(payload['metadata']['teacher_bot_session'],SESSION)


class StartTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_button_returns_existing_without_new_paid_request(self):
        db=AsyncMock();existing=capture()
        with patch.object(service.CalendarService,'lesson_access',AsyncMock(return_value=(lesson(),True))),patch.object(service,'session_for',AsyncMock(return_value=existing)):
            self.assertIs(await service.start(db,12,1),existing)
        db.commit.assert_not_awaited()

    async def test_student_or_foreign_teacher_rejected_before_config_and_requests(self):
        with patch.object(service.CalendarService,'lesson_access',AsyncMock(side_effect=ValueError('denied'))):
            with self.assertRaises(ValueError):await service.start(AsyncMock(),12,1)

    async def test_outside_time_window_and_cancelled_rejected(self):
        for item in [lesson(scheduled_at=NOW+timedelta(hours=2)),lesson(scheduled_at=NOW-timedelta(hours=2)),lesson(status=LessonStatus.CANCELLED)]:
            with patch.object(service.CalendarService,'lesson_access',AsyncMock(return_value=(item,True))),patch.object(service,'session_for',AsyncMock(return_value=None)),patch.object(service,'utcnow',return_value=NOW),patch.object(client,'configured',return_value=True),patch.object(service.settings,'RECALL_WEBHOOK_SECRET',Obj()),patch.object(service.settings,'RECALL_WEBHOOK_READY',True):
                with self.assertRaises(ValueError):await service.start(AsyncMock(),12,1)


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def run_job(self,row,item=None,analysis=None,existing=None):
        db=AsyncMock();db.add=MagicMock();item=item or lesson()
        db.get.side_effect=[row,Obj(teacher_id=item.teacher_id)]
        db.execute.side_effect=[result(item),result(row),result(analysis),result(existing)]
        ctx=AsyncMock();ctx.__aenter__.return_value=db
        with patch.object(worker,'AsyncSessionLocal',return_value=ctx),patch.object(worker,'utcnow',return_value=NOW):
            await worker.process_one(Obj(),row.id)
        return db

    async def test_queued_capture_never_joins_after_lesson_end(self):
        row=capture(state='queued',bot_id=None)
        with patch.object(client,'request',AsyncMock()) as request:
            await self.run_job(row,lesson(scheduled_at=NOW-timedelta(hours=2)))
        request.assert_not_awaited()
        self.assertEqual(row.error,'missed_start')

    async def test_erasure_is_committed_even_when_leave_call_fails(self):
        row=capture(state='analysis',leave_sent=False)
        db=AsyncMock();db.add=MagicMock()
        db.get.side_effect=[row,Obj(teacher_id=3)]
        db.execute.side_effect=[result(lesson()),result(row),result(Obj(workflow_state='sent')),result()]
        ctx=AsyncMock();ctx.__aenter__.return_value=db
        with patch.object(worker,'AsyncSessionLocal',return_value=ctx),patch.object(worker,'utcnow',return_value=NOW),patch.object(client,'request',AsyncMock(side_effect=client.RecallError('network_unknown'))):
            with self.assertRaises(client.RecallError): await worker.process_one(Obj(),row.id)
        db.commit.assert_awaited_once()
        self.assertIn('DELETE FROM transcripts',str(db.execute.call_args_list[3].args[0]))

    async def test_conducted_and_roles_both_required(self):
        row=capture(state='ready')
        db=await self.run_job(row)
        db.add.assert_not_called()
        row=capture(state='ready')
        db=await self.run_job(row,lesson(conducted_at=NOW))
        self.assertIsInstance(db.add.call_args.args[0],LessonAnalysis)
        self.assertEqual(row.state,'analysis')

    async def test_successful_create_and_metadata(self):
        row=capture(state='queued',bot_id=None,recording_id=None,transcript_id=None)
        with patch.object(client,'request',AsyncMock(return_value={'id':BOT})) as request:
            db=await self.run_job(row)
        self.assertEqual(row.state,'joining');self.assertEqual(row.bot_id,BOT)
        self.assertEqual(db.commit.await_count,2)
        self.assertEqual(request.call_args.args[2]['metadata']['teacher_bot_session'],SESSION)

    async def test_ambiguous_create_never_repeated_automatically(self):
        row=capture(state='queued',bot_id=None)
        with patch.object(client,'request',AsyncMock(side_effect=client.RecallError('network_unknown'))) as request:
            await self.run_job(row)
            self.assertEqual(row.state,'create_unknown')
            row.notice_sent=True
            await self.run_job(row)
        request.assert_awaited_once()

    async def test_capacity_error_retries_limited(self):
        row=capture(state='queued',bot_id=None)
        with patch.object(client,'request',AsyncMock(side_effect=client.RecallError('http_507'))):
            await self.run_job(row)
        self.assertEqual(row.state,'queued');self.assertEqual(row.next_attempt_at,NOW+timedelta(seconds=30))

    async def test_transcription_requested_in_auto_mode_once(self):
        row=capture(state='recorded',transcript_id=None)
        with patch.object(client,'request',AsyncMock(return_value={'id':TRANSCRIPT})) as request:
            await self.run_job(row)
            await self.run_job(row)
        request.assert_awaited_once()
        self.assertEqual(request.call_args.args[2]['provider'],{'recallai_async':{'language_code':'auto'}})

    async def test_download_does_not_analyze_or_mark_conducted(self):
        row=capture(state='download')
        payload=[{'participant':{'id':1},'words':[{'text':'Hello. Привіт.','start_timestamp':{'relative':1}}]}]
        with patch.object(client,'request',AsyncMock(return_value={'data':{'download_url':'https://example.com/file'}})),patch.object(client,'download',AsyncMock(return_value=payload)):
            item=lesson();db=await self.run_job(row,item)
        transcript=db.add.call_args.args[0]
        self.assertIsInstance(transcript,Transcript);self.assertEqual(transcript.source,'recall_unverified')
        self.assertEqual(row.state,'ready_roles');self.assertIsNone(item.conducted_at)

    async def test_delivery_failure_retains_transcript(self):
        row=capture(state='analysis')
        with patch.object(client,'request',AsyncMock()) as request:
            db=await self.run_job(row,analysis=Obj(workflow_state='send_failed'))
        self.assertEqual(row.cleanup_state,'none');request.assert_not_awaited()
        self.assertEqual(db.execute.await_count,3)

    async def test_sent_pdf_erases_local_before_remote_and_keeps_analysis(self):
        row=capture(state='analysis',leave_sent=True)
        with patch.object(client,'request',AsyncMock(return_value={})) as request:
            db=await self.run_job(row,analysis=Obj(workflow_state='sent'))
        self.assertEqual(row.cleanup_state,'done');self.assertEqual(row.state,'cleaned')
        self.assertIsNone(row.meeting_url)
        self.assertEqual([c.args[0] for c in request.call_args_list],['DELETE','DELETE'])
        self.assertIn('DELETE FROM transcripts',str(db.execute.call_args_list[3].args[0]))

    async def test_expired_transcript_blocks_analysis(self):
        row=capture(state='ready',expires_at=NOW-timedelta(seconds=1),leave_sent=True)
        analysis=Obj(workflow_state='queued',last_error=None)
        with patch.object(client,'request',AsyncMock(return_value={})):
            await self.run_job(row,analysis=analysis)
        self.assertEqual(analysis.workflow_state,'blocked')
        self.assertEqual(analysis.last_error,'transcript_expired')


class EventTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_and_out_of_order_events_do_not_regress_ready(self):
        row=capture(state='ready')
        event=Obj(event='recording.done',bot_id=BOT,session_id=SESSION,recording_id=RECORD,transcript_id=None,done=False)
        db=AsyncMock();db.execute.side_effect=[result(rows=[event]),result(row)]
        ctx=AsyncMock();ctx.__aenter__.return_value=db
        with patch.object(worker,'AsyncSessionLocal',return_value=ctx):await worker.consume_events()
        self.assertTrue(event.done);self.assertEqual(row.state,'ready')

    async def test_late_transcript_reactivates_remote_cleanup(self):
        row=capture(state='cleaned',cleanup_state='done',transcript_id=None)
        event=Obj(event='transcript.done',bot_id=BOT,session_id=SESSION,recording_id=RECORD,transcript_id=TRANSCRIPT,done=False)
        db=AsyncMock();db.execute.side_effect=[result(rows=[event]),result(row)]
        ctx=AsyncMock();ctx.__aenter__.return_value=db
        with patch.object(worker,'AsyncSessionLocal',return_value=ctx):await worker.consume_events()
        self.assertEqual(row.state,'cleanup');self.assertEqual(row.cleanup_state,'pending')
        self.assertEqual(row.transcript_id,TRANSCRIPT)

    async def test_unknown_bot_not_attached_by_meeting_url_or_lesson_guess(self):
        event=Obj(event='recording.done',bot_id=BOT,session_id=None,recording_id=RECORD,transcript_id=None,done=False)
        db=AsyncMock();db.execute.side_effect=[result(rows=[event]),result()]
        ctx=AsyncMock();ctx.__aenter__.return_value=db
        with patch.object(worker,'AsyncSessionLocal',return_value=ctx):await worker.consume_events()
        self.assertTrue(event.done);db.get.assert_not_awaited()

async def asgi_request(app, path, body=b'', headers=None, method='POST'):
    messages=[]
    async def receive():
        return {'type':'http.request','body':body,'more_body':False}
    async def send(message): messages.append(message)
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,
           'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'',
           'headers':[(k.encode(),v.encode()) for k,v in (headers or {}).items()],
           'client':('127.0.0.1',1234),'server':('localhost',8001),'root_path':''}
    await app(scope,receive,send)
    return messages[0]['status']


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_invalid_signatures_never_reach_database(self):
        from app import recall_gateway as gateway
        from pydantic import SecretStr
        with patch.object(gateway.settings,'RECALL_WEBHOOK_SECRET',SecretStr('whsec_dGVzdA==')),patch.object(gateway,'AsyncSessionLocal') as db:
            self.assertEqual(await asgi_request(gateway.app,'/webhooks/recall',b'{}'),401)
            self.assertEqual(await asgi_request(gateway.app,'/webhooks/recall',b'x'*65537),413)
        db.assert_not_called()
        self.assertEqual(await asgi_request(gateway.app,'/users',method='GET'),404)
        self.assertEqual(await asgi_request(gateway.app,'/docs',method='GET'),404)

    async def test_signed_webhook_persists_only_identifiers_and_deduplicates(self):
        from app import recall_gateway as gateway
        from pydantic import SecretStr
        body=json.dumps({'event':'recording.done','data':{'bot':{'id':BOT,'metadata':{'teacher_bot_session':SESSION}},'recording':{'id':RECORD},'unwanted':'PRIVATE TEXT'}}).encode()
        headers,secret=signed(body)
        db=AsyncMock();ctx=AsyncMock();ctx.__aenter__.return_value=db
        with patch.object(gateway.settings,'RECALL_WEBHOOK_SECRET',SecretStr(secret)),patch.object(gateway,'AsyncSessionLocal',return_value=ctx):
            response=await asgi_request(gateway.app,'/webhooks/recall',body,headers)
        self.assertEqual(response,200)
        statement=db.execute.call_args.args[0]
        self.assertIn('ON CONFLICT',str(statement))
        self.assertNotIn('PRIVATE TEXT',str(statement.compile().params))
        db.commit.assert_awaited_once()

class DownloadSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_literal_addresses_rejected_before_connect(self):
        for url in ('https://127.0.0.1/x','https://[::1]/x','https://169.254.169.254/x','http://example.com/x'):
            with self.assertRaises(client.RecallError) as caught:
                await client.download(url)
            self.assertEqual(caught.exception.code,'unsafe_download')
