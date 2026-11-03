"""Environment-backed settings for the local control panel."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    admin_username: str
    admin_password_hash: str
    session_secret: str
    host: str = "0.0.0.0"
    port: int = 7860
    public_ip_url: str = "https://api.ipify.org"
    session_hours: int = 12


def load_config() -> AppConfig:
    """Load required secrets and simple server settings from the environment."""
    _load_local_env()
    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    session_secret = os.getenv("SESSION_SECRET", "")
    if not password_hash or not session_secret:
        raise RuntimeError(
            "Set ADMIN_PASSWORD_HASH and SESSION_SECRET before starting the server. "
            "Generate a password hash with: python app.py --hash-password"
        )

    return AppConfig(
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_password_hash=password_hash,
        session_secret=session_secret,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "7860")),
        public_ip_url=os.getenv("PUBLIC_IP_URL", "https://api.ipify.org"),
        session_hours=int(os.getenv("SESSION_HOURS", "12")),
    )


def _load_local_env(env_file: Path | None = None) -> None:
    """Load simple KEY=value settings without overriding real environment variables."""
    env_file = env_file or Path(__file__).resolve().with_name(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name and name not in os.environ:
            os.environ[name] = value.strip('"\'')
