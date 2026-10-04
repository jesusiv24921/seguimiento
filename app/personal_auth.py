"""Acceso adicional a Personal. Nunca depende de un valor enviado por Dash."""
from functools import wraps
import hashlib
import hmac
import os
import secrets
from threading import Lock
import time
from urllib.parse import urlsplit

from flask import abort, has_request_context, redirect, render_template_string, request, session
from werkzeug.security import check_password_hash

SESSION_SECONDS = 30 * 60
_attempts = {}
_lock = Lock()


def password_hash():
    return os.environ.get("PERSONAL_PASSWORD_HASH", "")


def fingerprint():
    return hashlib.sha256(password_hash().encode()).hexdigest()


def authorized():
    if not has_request_context() or not password_hash():
        return False
    grant = session.get("personal_access", {})
    return (isinstance(grant, dict) and grant.get("credential") == fingerprint()
            and isinstance(grant.get("until"), (int, float)) and time.time() < grant["until"])


def require_access(function):
    @wraps(function)
    def protected(*args, **kwargs):
        if not authorized():
            abort(403, "Desbloquea Personal para continuar.")
        origin = request.headers.get("Origin")
        if request.method == "POST" and origin and urlsplit(origin).netloc != request.host:
            abort(403)
        return function(*args, **kwargs)
    return protected


_PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Acceso a Personal</title>
<style>body{font:16px system-ui;background:#f5f6f2;color:#20251f;margin:0;padding:24px}
main{max-width:420px;margin:10vh auto;background:white;border-radius:16px;padding:28px}
input,button{box-sizing:border-box;width:100%;padding:12px;margin:12px 0;border-radius:6px;border:1px solid #ccc}
button{background:#2464bb;color:white;cursor:pointer}a{color:#2464bb}.error{color:#9e2727}</style></head>
<body><main><h1>Personal</h1>
{% if error %}<p class="error" role="alert">{{error}}</p>{% endif %}
{% if unlocked %}<p>Tu acceso personal está desbloqueado.</p><p><a href="/personal">Volver a mis finanzas</a></p>
<form method="post" action="/personal/lock"><input type="hidden" name="csrf" value="{{csrf}}">
<button type="submit">Bloquear Personal</button></form>
{% elif configured %}<p>Ingresa tu clave de Personal.</p>
<form method="post"><input type="hidden" name="csrf" value="{{csrf}}">
<label for="password">Clave de Personal</label><input id="password" name="password" type="password"
autocomplete="current-password" required maxlength="512" autofocus><button type="submit">Entrar a Personal</button></form>
<p>El acceso caduca después de 30 minutos.</p>
{% else %}<p>Personal está bloqueado. Falta configurar su clave privada en el servidor.</p>{% endif %}
<p><a href="/">Volver al programa</a></p></main></body></html>"""


def install(server):
    if not server.secret_key:
        server.secret_key = os.environ.get("SEGUIMIENTO_SECRET_KEY") or secrets.token_hex(32)
    server.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    if os.environ.get("RENDER"):
        server.config["SESSION_COOKIE_SECURE"] = True

    def csrf():
        if not session.get("personal_csrf"):
            session["personal_csrf"] = secrets.token_urlsafe(32)
        return session["personal_csrf"]

    def check_csrf():
        token = session.get("personal_csrf")
        if not token or not hmac.compare_digest(token, request.form.get("csrf", "")):
            abort(403)

    @server.route("/personal/access", methods=["GET", "POST"])
    def personal_access():
        error, status = "", 200
        if request.method == "POST":
            check_csrf()
            session.pop("personal_access", None)
            encoded = password_hash()
            password = request.form.get("password", "")
            now = time.time()
            address = request.remote_addr or "unknown"
            with _lock:
                for key in list(_attempts):
                    if now - _attempts[key][0] >= 600:
                        del _attempts[key]
                first, count = _attempts.get(address, (now, 0))
                blocked = count >= 5 or (address not in _attempts and len(_attempts) >= 10000)
                if not blocked:
                    _attempts[address] = (first, count + 1)
            if blocked:
                error, status = "Demasiados intentos. Espera 10 minutos antes de volver a intentar.", 429
            else:
                try:
                    valid = bool(encoded and password and len(password) <= 512 and check_password_hash(encoded, password))
                except (ValueError, TypeError):
                    valid = False
                if valid:
                    session["personal_access"] = {"credential": fingerprint(), "until": now + SESSION_SECONDS}
                    session["personal_csrf"] = secrets.token_urlsafe(32)
                    with _lock:
                        _attempts.pop(address, None)
                    return redirect("/personal", code=303)
                error, status = "No se pudo desbloquear Personal. Revisa tu clave y la configuración.", 401
        return render_template_string(_PAGE, error=error, csrf=csrf(), unlocked=authorized(), configured=bool(password_hash())), status

    @server.post("/personal/lock")
    def personal_lock():
        check_csrf()
        session.pop("personal_access", None)
        session["personal_csrf"] = secrets.token_urlsafe(32)
        return redirect("/personal/access", code=303)

    @server.after_request
    def no_cache_personal(response):
        if request.path.startswith("/personal") or request.path.startswith("/_dash"):
            response.headers["Cache-Control"] = "no-store"
        if request.path.startswith("/personal"):
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "same-origin"
        return response
