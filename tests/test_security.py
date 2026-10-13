"""Run with APP_MODE=production, APP_ACCESS_PASSWORD, APP_SESSION_SECRET set."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['AI_FILM_DATA'] = tempfile.mkdtemp(prefix='film-studio-auth-test-')
from fastapi.testclient import TestClient
from backend.main import app
from backend.security import PASSWORD, REQUIRE_AUTH, SECRET, valid_cookie
assert REQUIRE_AUTH and len(PASSWORD)>=12 and len(SECRET)>=32
with TestClient(app,base_url='https://film.example') as client:
    assert client.get('/api/health').status_code==200
    assert client.get('/').status_code==200  # Follows redirect to /login
    response=client.get('/api/projects')
    assert response.status_code==401,response.text
    assert client.get('/media/characters/MAI_REF.png').status_code==401
    assert client.get('/assets/studio.css').status_code==401
    assert client.post('/auth/login',json={'password':'bad'}).status_code==401
    # login with a cookie that only the server signs
    response=client.post('/auth/login',json={'password':PASSWORD})
    assert response.status_code==200,response.text
    cookie=client.cookies.get('film_studio_session')
    assert cookie and valid_cookie(cookie)
    assert 'httponly' in response.headers.get('set-cookie','').lower()
    assert 'secure' in response.headers.get('set-cookie','').lower()
    assert client.get('/api/projects').status_code==200
    assert client.get('/').status_code==200
    assert client.post('/api/projects',json={'title':'Tập thử','story':'Một câu chuyện về cô lao công phát hiện sai sót trong hợp đồng quan trọng.','minutes':8},headers={'Origin':'https://attacker.example'}).status_code==403
    assert client.post('/auth/logout').status_code==200
    assert client.get('/api/projects').status_code==401
print('TEST PASSED: public deployment password gate, session, media/API protection, CSRF and logout')
