"""Recall API adapter. Never log credentials, signed URLs or response bodies."""
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import socket
import time
from uuid import UUID
from urllib.parse import urlsplit
import aiohttp
from aiohttp.abc import AbstractResolver
from app.config import settings

BASES = {f'https://{region}.recall.ai' for region in
         ('eu-central-1','us-east-1','us-west-2','ap-northeast-1')}


class RecallError(Exception):
    def __init__(self, code):
        self.code=code
        super().__init__(code)


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise RecallError('invalid_id') from None


def configured():
    return bool(settings.RECALL_API_KEY and settings.RECALL_API_KEY.get_secret_value().strip()
                and settings.RECALL_BASE_URL.rstrip('/') in BASES)


def verify_signature(body, headers, secret, now=None):
    try:
        msg_id=headers['webhook-id']; stamp=headers['webhook-timestamp']
        signatures=headers['webhook-signature']
        if not secret.startswith('whsec_') or not 0 < len(msg_id) <= 255:
            raise ValueError()
        if abs((now if now is not None else time.time())-int(stamp)) > 300:
            raise ValueError()
        key=base64.b64decode(secret[6:],validate=True)
        if not key: raise ValueError()
        expected=base64.b64encode(hmac.new(key,msg_id.encode()+b'.'+stamp.encode()+b'.'+body,hashlib.sha256).digest()).decode()
        if not any(hmac.compare_digest('v1,'+expected,sig) for sig in signatures.split()):
            raise ValueError()
        return msg_id
    except (KeyError,ValueError,TypeError):
        raise RecallError('invalid_signature') from None


async def read_json(response, limit=8*1024*1024):
    data=bytearray()
    async for chunk in response.content.iter_chunked(65536):
        data.extend(chunk)
        if len(data)>limit: raise RecallError('response_too_large')
    if not data: return {}
    try:
        return json.loads(data)
    except (ValueError,UnicodeDecodeError):
        raise RecallError('invalid_response') from None


def safe_error_detail(data, payload=None):
    """Only validation fields/messages; discard reflected request values and secrets."""
    secrets=[]
    def collect(value):
        if isinstance(value, dict):
            for child in value.values(): collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
        elif isinstance(value, str) and value: secrets.append(value)
    collect(payload)
    for name in ('RECALL_API_KEY','RECALL_WEBHOOK_SECRET','GEMINI_API_KEY','TELEGRAM_BOT_TOKEN','POSTGRES_PASSWORD','TEACHER_REGISTRATION_CODE'):
        value=getattr(settings,name,None)
        if value:
            secrets.append(value.get_secret_value() if hasattr(value,'get_secret_value') else str(value))
    allowed={'detail','error','errors','message','non_field_errors','meeting_url','bot_name',
        'recording_config','audio_mixed_mp3','audio_separate_mp3','video_mixed_mp4',
        'retention','type','hours','automatic_leave','waiting_room_timeout','noone_joined_timeout',
        'everyone_left_timeout','timeout','activate_after','in_call_not_recording_timeout',
        'in_call_recording_timeout','provider','recallai_async','language_code','diarization',
        'use_separate_streams_when_available'}
    lines=[]
    def visit(value, path='', depth=0):
        if depth>8 or len(lines)>=8: return
        if isinstance(value,dict):
            for key,child in value.items():
                if key in allowed: visit(child, (path+'.' if path else '')+key, depth+1)
        elif isinstance(value,list):
            for child in value[:8]: visit(child,path,depth+1)
        elif isinstance(value,str):
            for secret in sorted(set(secrets),key=len,reverse=True): value=value.replace(secret,'[redacted]')
            value=re.sub(r'https?://[^\s<>]+','[url]',value)
            value=re.sub(r'[\w.+-]+@[\w.-]+','[email]',value)
            value=re.sub(r'\b[A-Za-z0-9_+/=-]{24,}\b','[identifier]',value)
            value=' '.join(value.split())[:300]
            if value: lines.append((path+': ' if path else '')+value)
    # Never log an unstructured HTML/text proxy response.
    if isinstance(data,(dict,list)): visit(data)
    return '; '.join(lines)[:1200] or 'No safe structured validation detail available'


async def request(method, path, payload=None):
    if not configured(): raise RecallError('not_configured')
    if not path.startswith('/api/v1/'): raise RecallError('invalid_path')
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as client:
            async with client.request(method, settings.RECALL_BASE_URL.rstrip('/')+path,
                headers={'Authorization':settings.RECALL_API_KEY.get_secret_value()},
                json=payload,allow_redirects=False) as response:
                if method=='DELETE' and response.status==404: return {}
                if not 200 <= response.status < 300:
                    try:
                        detail=safe_error_detail(await read_json(response,limit=16384),payload)
                    except (RecallError,aiohttp.ClientError,asyncio.TimeoutError):
                        detail='Error response unavailable or not valid bounded JSON'
                    logging.getLogger(__name__).warning('Recall API %s HTTP %s: %s',method,response.status,detail)
                    raise RecallError(f'http_{response.status}')
                return await read_json(response)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise RecallError('network_unknown' if method=='POST' else 'network') from None


class PublicResolver(AbstractResolver):
    """Resolve once and reject private/local destinations before opening the socket."""
    async def resolve(self, host, port=0, family=socket.AF_INET):
        answers=await asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM,family=family)
        result=[]
        for fam,_,proto,_,addr in answers:
            if not ipaddress.ip_address(addr[0]).is_global:
                raise RecallError('unsafe_download')
            result.append(dict(hostname=host,host=addr[0],port=port,family=fam,proto=proto,flags=socket.AI_NUMERICHOST))
        return result
    async def close(self): pass


async def download(url):
    # URL comes from an authenticated Recall response, never a webhook payload.
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.port not in (None,443):
        raise RecallError('unsafe_download')
    try:
        address=ipaddress.ip_address(parts.hostname)
    except ValueError:
        address=None
    if address is not None and not address.is_global:
        raise RecallError('unsafe_download')
    try:
        connector=aiohttp.TCPConnector(resolver=PublicResolver())
        async with aiohttp.ClientSession(connector=connector,timeout=aiohttp.ClientTimeout(total=60)) as client:
            async with client.get(url,allow_redirects=False) as response:
                if response.status!=200: raise RecallError('download_failed')
                return await read_json(response)
    except (aiohttp.ClientError,asyncio.TimeoutError):
        raise RecallError('download_failed') from None


def bot_payload(row):
    return {'meeting_url':row.meeting_url,'bot_name':'Помічник викладача',
        'metadata':{'teacher_bot_session':row.id},
        'recording_config':{'audio_mixed_mp3':{},'audio_separate_mp3':{},'video_mixed_mp4':None,
                            'retention':{'type':'timed','hours':168}},
        'automatic_leave':{'waiting_room_timeout':300,'noone_joined_timeout':300,
                           'everyone_left_timeout':{'timeout':60,'activate_after':1},
                           'in_call_not_recording_timeout':300,
                           'in_call_recording_timeout':max(60,int((row.stop_at-row.created_at).total_seconds()))}}


def transcript_text(payload):
    if not isinstance(payload,list): raise RecallError('invalid_transcript')
    lines=[]
    for turn in payload:
        try:
            words=turn['words']; participant=turn.get('participant') or {}
            if not words: continue
            text=' '.join(word['text'] for word in words).strip()
            if not text: continue
            seconds=float(words[0]['start_timestamp']['relative'])
            if not 0<=seconds<86400: raise ValueError()
            speaker=str(participant.get('id','unknown'))[:40]
            # Display names are not trusted role evidence. Gemini must not guess teacher/student.
            name=str(participant.get('name') or 'Невідомий учасник').replace('\n',' ')[:100]
            lines.append(f'[{int(seconds)//60:02d}:{int(seconds)%60:02d}] Учасник {speaker} ({name}): {text}')
        except (KeyError,TypeError,ValueError):
            raise RecallError('invalid_transcript') from None
    value='\n'.join(lines)
    if not value or '\x00' in value: raise RecallError('empty_transcript')
    if len(value)>200000: raise RecallError('transcript_too_long')
    return value
