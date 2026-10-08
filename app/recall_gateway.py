"""Public webhook-only app. Do NOT expose the legacy unauthenticated CRUD API."""
import json
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy.dialects.postgresql import insert
from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import RecallEvent
from app.services.calendar_service import utcnow
from app.services.recall_client import verify_signature, identifier, RecallError

app=FastAPI(title='Recall webhook receiver',docs_url=None,redoc_url=None,openapi_url=None)
EVENTS={'recording.done','recording.failed','recording.deleted','transcript.done','transcript.failed',
        'bot.joining_call','bot.in_waiting_room','bot.in_call_recording','bot.call_ended','bot.done','bot.fatal'}


@app.get('/health')
async def health():
    return {'status':'ok'}


@app.post('/webhooks/recall')
async def webhook(request: Request):
    if not settings.RECALL_WEBHOOK_SECRET:
        raise HTTPException(503,'Webhook not configured')
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>65536: raise HTTPException(413,'Payload too large')
    try:
        event_id=verify_signature(bytes(body),request.headers,settings.RECALL_WEBHOOK_SECRET.get_secret_value())
    except RecallError:
        raise HTTPException(401,'Invalid signature') from None
    try:
        payload=json.loads(body)
        event=payload['event']
        if event not in EVENTS: return {'accepted':True}
        data=payload['data']; bot=data['bot']
        meta=bot.get('metadata') or {}
        fields=dict(id=event_id,event=event,bot_id=identifier(bot['id']),
            session_id=identifier(meta['teacher_bot_session']) if meta.get('teacher_bot_session') else None,
            recording_id=identifier(data['recording']['id']) if data.get('recording') else None,
            transcript_id=identifier(data['transcript']['id']) if data.get('transcript') else None,
            created_at=utcnow(),done=False)
    except (ValueError,TypeError,KeyError,AttributeError,RecallError):
        raise HTTPException(400,'Invalid event') from None
    async with AsyncSessionLocal() as session:
        await session.execute(insert(RecallEvent).values(**fields).on_conflict_do_nothing(index_elements=['id']))
        await session.commit()
    return {'accepted':True}
