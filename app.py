"""Little Daemon: a small authenticated control panel for one Windows PC."""

import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import ipaddress
import logging
import platform
import socket
import time
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from argon2 import PasswordHasher
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import Auth
from actions import load_actions, run_action
from config import AppConfig, load_config


BASE_DIR = Path(__file__).resolve().parent
STARTED_AT = time.monotonic()
LOG = logging.getLogger("little-daemon")


def local_ip() -> str:
    """Find the address used for outbound traffic without sending any data."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


async def public_ip(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            value = (await client.get(url)).text.strip()
        address = ipaddress.ip_address(value)
        return value if address.version == 4 and address.is_global else None
    except (httpx.HTTPError, ValueError):
        return None


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="Little Daemon")
    auth = Auth(
        config.admin_username,
        config.admin_password_hash,
        config.session_secret,
        config.session_hours,
    )
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    actions = load_actions(BASE_DIR / "data" / "config.json")

    def require_api_user(request: Request) -> str:
        user = auth.user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if auth.user(request):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(request, "login.html", {"error": None})

    @app.post("/login", response_class=HTMLResponse)
    async def login(request: Request):
        form = parse_qs((await request.body()).decode("utf-8"))
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        if not auth.verify_password(username, password, request.client.host if request.client else "unknown"):
            LOG.warning("login failure username=%s", username or "<empty>")
            await asyncio.sleep(0.1)
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Invalid credentials."},
                status_code=401,
            )

        LOG.info("login success username=%s", username)
        response = RedirectResponse("/", status_code=303)
        auth.set_session(response)
        return response

    @app.post("/logout")
    async def logout(request: Request):
        response = RedirectResponse("/login", status_code=303)
        auth.clear_session(response)
        return response

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        if not auth.user(request):
            return RedirectResponse("/login", status_code=303)
        return templates.TemplateResponse(
            request,
            "index.html",
            {"username": config.admin_username, "port": config.port},
        )

    @app.get("/api/status")
    async def status(_: str = Depends(require_api_user)):
        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "local_ip": local_ip(),
            "public_ip": await public_ip(config.public_ip_url),
            "server": {"host": config.host, "port": config.port},
            "uptime_seconds": int(time.monotonic() - STARTED_AT),
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.get("/api/actions")
    async def list_actions(_: str = Depends(require_api_user)):
        return [
            {"id": action.id, "label": action.label, "type": action.type, "confirm": action.confirm}
            for action in actions.values()
        ]

    @app.post("/api/actions/{action_id}")
    async def execute_action(action_id: str, user: str = Depends(require_api_user)):
        action = actions.get(action_id)
        if not action:
            raise HTTPException(status_code=404, detail="Unknown action")
        LOG.info("action invocation user=%s action=%s", user, action.id)
        result = run_action(action)
        LOG.info("action result user=%s action=%s ok=%s", user, action.id, result["ok"])
        return {"action": action.id, **result}

    return app


def hash_password() -> None:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Repeat password: ")
    if not first or first != second:
        raise SystemExit("Passwords are empty or do not match.")
    print(PasswordHasher().hash(first))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash-password", action="store_true", help="print an Argon2 password hash")
    args = parser.parse_args()
    if args.hash_password:
        hash_password()
        return

    import uvicorn

    config = load_config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    LOG.info("starting server host=%s port=%s", config.host, config.port)
    uvicorn.run(create_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
