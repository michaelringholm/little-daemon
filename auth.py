"""Small signed-cookie authentication helper."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from starlette.requests import Request
from starlette.responses import Response


COOKIE_NAME = "little_daemon_session"
PASSWORDS = PasswordHasher()


class Auth:
    def __init__(self, username: str, password_hash: str, secret: str, session_hours: int = 12):
        self.username = username
        self.password_hash = password_hash
        self.secret = secret.encode("utf-8")
        self.max_age = session_hours * 60 * 60
        self._failures: dict[str, tuple[int, float]] = {}

    def verify_password(self, username: str, password: str, client_ip: str) -> bool:
        """Verify credentials and apply a short in-memory login lockout."""
        now = time.monotonic()
        count, locked_until = self._failures.get(client_ip, (0, 0))
        if locked_until > now:
            return False

        valid = username == self.username
        try:
            valid = valid and PASSWORDS.verify(self.password_hash, password)
        except (VerifyMismatchError, VerificationError):
            valid = False

        if valid:
            self._failures.pop(client_ip, None)
            return True

        count += 1
        self._failures[client_ip] = (count, now + 60 if count >= 5 else 0)
        return False

    def set_session(self, response: Response) -> None:
        expires = int(time.time()) + self.max_age
        payload = {"user": self.username, "expires": expires, "nonce": secrets.token_urlsafe(12)}
        encoded = _encode(payload)
        signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        response.set_cookie(
            COOKIE_NAME,
            f"{encoded}.{signature}",
            max_age=self.max_age,
            httponly=True,
            samesite="strict",
            path="/",
        )

    def user(self, request: Request) -> str | None:
        value = request.cookies.get(COOKIE_NAME, "")
        try:
            encoded, signature = value.rsplit(".", 1)
            expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(_decode(encoded))
            if payload["user"] != self.username or int(payload["expires"]) < time.time():
                return None
            return payload["user"]
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def clear_session(response: Response) -> None:
        response.delete_cookie(COOKIE_NAME, path="/")


def _encode(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(value: str) -> str:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
