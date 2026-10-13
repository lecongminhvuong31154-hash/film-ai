"""Single-studio password gate for public deployment.

Public repository source remains visible; this protects runtime UI/API/media only.
Never commit APP_ACCESS_PASSWORD or APP_SESSION_SECRET.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

MODE = os.getenv('APP_MODE', 'local').strip().lower()
PASSWORD = os.getenv('APP_ACCESS_PASSWORD', '')
SECRET = os.getenv('APP_SESSION_SECRET', '')
REQUIRE_AUTH = MODE == 'production' or os.getenv('APP_REQUIRE_AUTH') == '1'
COOKIE = 'film_studio_session'
TTL = 12 * 3600
_PUBLIC = {'/api/health','/robots.txt','/login','/auth/login','/auth/login.css','/auth/login.js','/auth/logout'}
LOCK = threading.Lock()
ATTEMPTS = defaultdict(deque)


def is_configured():
    if not REQUIRE_AUTH:
        return True
    return len(PASSWORD) >= 12 and len(SECRET) >= 32


def _key():
    # Rotating the password also invalidates previously signed sessions.
    return hashlib.sha256((SECRET + '\x00' + PASSWORD).encode('utf-8')).digest()


def _signature(payload):
    return hmac.new(_key(),payload.encode('ascii'),hashlib.sha256).hexdigest()


def make_cookie():
    expiry = int(time.time()) + TTL
    payload = str(expiry) + '.' + secrets.token_urlsafe(18)
    raw = payload + '.' + _signature(payload)
    return base64.urlsafe_b64encode(raw.encode('ascii')).decode('ascii').rstrip('=')


def valid_cookie(cookie):
    if not cookie or not is_configured():
        return False
    try:
        pad = '=' * (-len(cookie) % 4)
        raw = base64.urlsafe_b64decode(cookie + pad).decode('ascii')
        expiry, nonce, sig = raw.split('.', 2)
        payload = expiry + '.' + nonce
        return int(expiry) >= int(time.time()) and hmac.compare_digest(sig, _signature(payload))
    except (ValueError, UnicodeDecodeError, TypeError):
        return False


def _https(request):
    # Render / reverse proxies set x-forwarded-proto to https.
    return MODE == 'production' or request.url.scheme == 'https' or (request.headers.get('x-forwarded-proto','').split(',')[0].strip() == 'https')


def _same_origin(request):
    origin = request.headers.get('origin')
    if not origin:
        return True  # SameSite=Strict cookie protects normal browsers on requests with no Origin.
    from urllib.parse import urlsplit
    try:
        o = urlsplit(origin)
        host = request.headers.get('host','')
        return o.scheme in ('http','https') and o.netloc == host and o.scheme == ('https' if _https(request) else 'http')
    except ValueError:
        return False


def _too_many(client_ip):
    now=time.time()
    with LOCK:
        q=ATTEMPTS[client_ip]
        while q and q[0] < now-600:
            q.popleft()
        if len(q)>=8:
            return True
        q.append(now)
        if len(ATTEMPTS)>2000:
            ATTEMPTS.clear()  # Bounded in-memory protection for this single-instance MVP.
        return False


class PasswordGate(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path=request.url.path
        configured=is_configured()
        if path == '/api/health':
            return await call_next(request)
        if REQUIRE_AUTH and not configured:
            return HTMLResponse('Studio chưa cấu hình APP_ACCESS_PASSWORD (từ 12 ký tự) và APP_SESSION_SECRET (từ 32 ký tự).',status_code=503)
        if not REQUIRE_AUTH and request.client and request.client.host not in ('127.0.0.1','::1','localhost','testclient'):
            return JSONResponse({'detail':'Local Studio chỉ cho phép truy cập từ chính máy tính.'},status_code=403)
        if REQUIRE_AUTH and path not in _PUBLIC and not valid_cookie(request.cookies.get(COOKIE)):
            if path.startswith('/api/') or path.startswith('/media/') or path.startswith('/assets/') or path in ('/docs','/redoc','/openapi.json'):
                response=JSONResponse({'detail':'Chưa đăng nhập','login':'/login'},status_code=401)
            else:
                response=RedirectResponse('/login',status_code=303)
        elif REQUIRE_AUTH and request.method in ('POST','PUT','PATCH','DELETE') and not _same_origin(request):
            response=JSONResponse({'detail':'Origin không hợp lệ'},status_code=403)
        else:
            response=await call_next(request)
        # Never cache protected pages or video metadata.
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Robots-Tag']='noindex, nofollow'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        if _https(request):
            response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
        return response


router=APIRouter()
PUBLIC_DIR=Path(__file__).parent/'public'


@router.get('/login')
def login_page(request: Request):
    if not REQUIRE_AUTH:
        return RedirectResponse('/',status_code=303)
    if valid_cookie(request.cookies.get(COOKIE)):
        return RedirectResponse('/',status_code=303)
    return HTMLResponse((PUBLIC_DIR/'login.html').read_text(encoding='utf-8'))


@router.get('/auth/login.css')
def login_styles():
    return Response((PUBLIC_DIR/'login.css').read_text(encoding='utf-8'),media_type='text/css')


@router.get('/auth/login.js')
def login_script():
    return Response((PUBLIC_DIR/'login.js').read_text(encoding='utf-8'),media_type='application/javascript')


class LoginInput(BaseModel):
    password: str=Field(min_length=1,max_length=512)


@router.post('/auth/login')
def login(request:Request,payload:LoginInput):
    if not REQUIRE_AUTH:
        return JSONResponse({'ok':True})
    ip=request.client.host if request.client else 'unknown'
    if _too_many(ip):
        return JSONResponse({'detail':'Thử quá nhiều lần. Vui lòng đợi 10 phút.'},status_code=429)
    if not hmac.compare_digest(payload.password.encode('utf-8'),PASSWORD.encode('utf-8')):
        return JSONResponse({'detail':'Mật khẩu không đúng'},status_code=401)
    with LOCK:
        ATTEMPTS.pop(ip,None)
    response=JSONResponse({'ok':True})
    response.set_cookie(COOKIE,make_cookie(),httponly=True,secure=_https(request),samesite='strict',max_age=TTL,path='/')
    return response


@router.get('/auth/status')
def status(request:Request):
    return {'enabled':REQUIRE_AUTH,'authenticated':not REQUIRE_AUTH or valid_cookie(request.cookies.get(COOKIE))}


@router.post('/auth/logout')
def logout():
    response=JSONResponse({'ok':True})
    response.delete_cookie(COOKIE,path='/')
    return response


@router.get('/robots.txt')
def robots():
    return Response('User-agent: *\nDisallow: /\n',media_type='text/plain')
