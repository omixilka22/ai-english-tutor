"""Run from the project: python -m app.check_gemini [--probe]. No lesson data is sent."""
import argparse
import asyncio
import json
import re
import aiohttp
from app.config import settings
from app.services import gemini_analysis

async def main(probe=False):
    if not gemini_analysis.configured():
        print('GEMINI_API_KEY is not configured.'); return
    model = settings.GEMINI_MODEL
    if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        print('Invalid GEMINI_MODEL value.'); return
    print('Configured model:', model)
    models = []
    token = None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as client:
            for _ in range(20):
                params = {'pageSize': 1000}
                if token: params['pageToken'] = token
                async with client.get('https://generativelanguage.googleapis.com/v1beta/models',
                    params=params, headers={'x-goog-api-key': settings.GEMINI_API_KEY.get_secret_value()},
                    allow_redirects=False) as response:
                    print('Models API HTTP:', response.status)
                    if response.status != 200:
                        print('Could not verify model availability. No settings changed.'); return
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        data.extend(chunk)
                        if len(data) > 2 * 1024 * 1024:
                            print('Unexpectedly large models response.'); return
                    payload = json.loads(data)
                    models.extend(item['name'].removeprefix('models/') for item in payload.get('models', [])
                                  if 'generateContent' in item.get('supportedGenerationMethods', [])
                                  and re.fullmatch(r'models/[A-Za-z0-9._-]+', item.get('name', '')))
                    token = payload.get('nextPageToken')
                    if not token: break
        print('Configured model supports generateContent:', model in models)
        print('Available Flash models:', ', '.join(name for name in models if 'flash' in name))
        if probe and model in models:
            print('Testing with a synthetic dialogue; no real transcript.')
            try:
                await gemini_analysis.analyze('Teacher: What did you do yesterday? Student: I went to school.')
            except gemini_analysis.AnalysisError as error:
                print('Analysis test:', error.code)
            else:
                print('Analysis test: OK, all four blocks validated.')
        elif probe:
            print('Probe skipped: configured model not found. Choose an available model in .env and restart.')
    except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, KeyError) as error:
        print('Diagnostic failed:', type(error).__name__)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', help='Test one synthetic dialogue (uses API quota).')
    asyncio.run(main(parser.parse_args().probe))
