"""Personal uses the application login, without a second password."""
from functools import wraps
from urllib.parse import urlsplit
from flask import abort, redirect, request


def require_access(function):
    @wraps(function)
    def protected(*args, **kwargs):
        origin = request.headers.get("Origin")
        if request.method == "POST" and origin and urlsplit(origin).netloc != request.host:
            abort(403)
        return function(*args, **kwargs)
    return protected


def install(server):
    @server.route("/personal/access", methods=["GET", "POST"])
    @server.route("/personal/lock", methods=["GET", "POST"])
    def personal_access():
        return redirect("/personal", code=303)

    @server.after_request
    def no_cache_personal(response):
        if request.path.startswith("/personal") or request.path.startswith("/_dash"):
            response.headers["Cache-Control"] = "no-store"
        if request.path.startswith("/personal"):
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "same-origin"
        return response
