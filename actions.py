"""Explicitly allowlisted local actions; never execute browser-supplied commands."""

from dataclasses import dataclass
import json
import logging
import ctypes
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import time
from urllib.request import urlopen


LOG = logging.getLogger("little-daemon.actions")
OUTPUT_LIMIT = 20_000


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    type: str
    command: str | None = None
    confirm: bool = False


BUILTINS = {
    "machine_info": lambda: f"hostname={socket.gethostname()}\nplatform={platform.platform()}",
    "local_ip": lambda: _local_ip(),
    "public_ip": lambda: _public_ip(),
    "disk_free": lambda: _disk_free(),
    "memory": lambda: _fixed_command(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory,TotalVisibleMemorySize | Format-List"]
    ),
    "uptime": lambda: _uptime(),
    "network_config": lambda: _fixed_command(["ipconfig.exe", "/all"]),
    "running_processes": lambda: _fixed_command(["tasklist.exe", "/FO", "TABLE", "/NH"]),
    "listening_ports": lambda: _fixed_command(["netstat.exe", "-ano", "-p", "TCP"]),
    "restart_pc": lambda: _fixed_command(
        ["shutdown.exe", "/r", "/t", "30", "/c", "Restart requested from Little Daemon"]
    ),
    "shutdown_pc": lambda: _fixed_command(
        ["shutdown.exe", "/s", "/t", "30", "/c", "Shutdown requested from Little Daemon"]
    ),
}


def load_actions(path: Path) -> dict[str, Action]:
    if not path.exists():
        return {name: Action(name, name.replace("_", " ").title(), "builtin") for name in BUILTINS}

    data = json.loads(path.read_text(encoding="utf-8"))
    actions = {}
    for item in data.get("actions", []):
        action = Action(item["id"], item["label"], item["type"], item.get("command"), item.get("confirm", False))
        if action.type not in {"builtin", "script"} or action.id in actions:
            raise ValueError(f"Invalid or duplicate action: {action.id}")
        if action.type == "builtin" and action.id not in BUILTINS:
            raise ValueError(f"Unknown builtin action: {action.id}")
        if action.type == "script":
            if not action.command or not Path(action.command).is_file():
                raise ValueError(f"Configured script does not exist: {action.command}")
        actions[action.id] = action
    return actions


def run_action(action: Action, timeout: int = 30) -> dict:
    started = time.monotonic()
    try:
        if action.type == "builtin":
            output, exit_code = BUILTINS[action.id](), 0
        else:
            command = _script_command(Path(action.command))
            result = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(Path(action.command).parent),
            )
            output, exit_code = result.stdout + result.stderr, result.returncode
        return {
            "ok": exit_code == 0,
            "exit_code": exit_code,
            "output": output[-OUTPUT_LIMIT:],
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "output": "Action timed out.", "duration_ms": timeout * 1000}
    except (OSError, KeyError, RuntimeError) as error:
        return {"ok": False, "exit_code": None, "output": str(error), "duration_ms": 0}


def _script_command(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".ps1":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    if suffix in {".bat", ".cmd"}:
        return ["cmd.exe", "/d", "/c", str(path)]
    return [str(path)]


def _local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _disk_free() -> str:
    usage = shutil.disk_usage(Path.cwd().anchor or Path.cwd())
    return f"free_gb={usage.free / (1024 ** 3):.1f}\ntotal_gb={usage.total / (1024 ** 3):.1f}"


def _public_ip() -> str:
    try:
        with urlopen("https://api.ipify.org", timeout=3) as response:
            return response.read().decode().strip()
    except (OSError, UnicodeError):
        return "unavailable"


def _uptime() -> str:
    if os.name == "nt":
        seconds = ctypes.windll.kernel32.GetTickCount64() / 1000
    else:
        seconds = time.monotonic()
    return f"uptime_hours={seconds / 3600:.1f}"


def _fixed_command(command: list[str]) -> str:
    try:
        result = subprocess.run(command, shell=False, capture_output=True, text=True, timeout=15)
        output = (result.stdout + result.stderr).strip()
        if result.returncode:
            raise RuntimeError(output or f"exit_code={result.returncode}")
        return output or f"exit_code={result.returncode}"
    except OSError as error:
        raise RuntimeError(str(error)) from error
