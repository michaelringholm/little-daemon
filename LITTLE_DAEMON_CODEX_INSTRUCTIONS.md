# Little Daemon — Codex Build Instructions

## Goal

Turn the current tiny Python web server into a very small self-hosted control panel for one Windows PC.

The app should remain simple, understandable, and easy to run locally.

Primary goals:

1. Password-protect the web UI.
2. Allow the UI to trigger a small set of explicitly configured actions on the PC.
3. Run a background heartbeat daemon that periodically calls an AWS endpoint so AWS always knows the current public IP.
4. Configure the heartbeat/AWS settings through the web UI.
5. Keep the design minimal and secure enough for a home-server utility exposed through router port forwarding.

Do not turn this into a large framework-heavy application.

---

## Current Environment

The machine currently has:

- Local IP: `192.168.1.101`
- Web port: `7860`
- Router forwards external TCP `7860` to `192.168.1.101:7860`
- Current public IP observed during testing: `89.150.157.33`
- Current external test URL: `http://89.150.157.33:7860`

The existing app is a basic Python HTTP server listening on:

```text
0.0.0.0:7860
```

Keep port `7860` configurable but use it as the default.

---

# 1. Technology

Prefer a tiny stack:

- Python 3.11+
- FastAPI
- Uvicorn
- Jinja2 templates, or very small server-rendered HTML
- SQLite only if useful
- Standard Python logging
- `httpx` for outbound HTTP calls

Avoid React, Node, Docker, Redis, Celery, or other unnecessary infrastructure.

Suggested structure:

```text
little-daemon/
├── app.py
├── config.py
├── auth.py
├── actions.py
├── heartbeat.py
├── models.py
├── templates/
│   ├── login.html
│   └── index.html
├── static/
│   └── app.css
├── data/
│   └── config.json
├── .env.example
├── requirements.txt
└── README.md
```

Keep the implementation compact.

---

# 2. Password Protection

The entire control panel must require authentication.

Use:

- one configured admin username
- one admin password
- password stored as a secure password hash, never plaintext
- session cookie after login
- `HttpOnly`
- `SameSite=Strict`
- session timeout, default 12 hours

Use `argon2-cffi` or `bcrypt`.

Configuration can initially come from environment variables:

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=...
SESSION_SECRET=...
```

Add a helper command for generating a password hash.

For example:

```powershell
python app.py --hash-password
```

Never log the password.

Add basic login throttling, such as a short delay or temporary lockout after repeated failed attempts.

---

# 3. Important Security Rule: No Arbitrary Remote Shell

Do NOT build a general-purpose remote shell, terminal, PowerShell console, `cmd.exe` endpoint, or an API that accepts arbitrary commands from the browser.

The control panel may trigger local functionality, but only through an explicit allowlist.

Use a configuration model like:

```json
{
  "actions": [
    {
      "id": "restart_media_studio",
      "label": "Restart Media Studio",
      "type": "script",
      "command": "D:\\scripts\\restart-media-studio.ps1"
    },
    {
      "id": "check_disk",
      "label": "Check Disk Space",
      "type": "builtin"
    }
  ]
}
```

The browser sends only:

```text
POST /api/actions/restart_media_studio
```

The backend resolves `restart_media_studio` to a predefined action.

The browser must never submit raw shell commands.

For configured scripts:

- script path must already exist in configuration
- no user-supplied arguments initially
- use `subprocess.run`
- `shell=False`
- timeout, default 30 seconds
- capture stdout/stderr
- cap returned output, e.g. 20 KB
- log who invoked it and whether it succeeded

Support these action categories:

### Built-in actions

Useful initial built-ins:

- hostname / machine info
- current local IP
- current public IP
- disk free space
- CPU/memory overview
- uptime
- list configured local services
- check whether a configured TCP port is listening

### Script actions

Allow the owner to register explicit `.ps1`, `.bat`, or executable paths.

Do not permit arbitrary arguments from remote requests in v1.

---

# 4. Control Panel UI

Make one small clean page after login.

Suggested sections:

## Status

Show:

- hostname
- local IP
- current public IP
- server uptime
- heartbeat status
- last successful heartbeat
- last IP sent to AWS
- next heartbeat
- configured AWS endpoint
- current port

## Actions

Display configured local actions as buttons.

Examples:

```text
[ Restart Media Studio ]
[ Check Disk Space ]
[ Check Port 8000 ]
```

When clicked:

- ask for a small confirmation for potentially disruptive actions
- POST to backend
- show output and exit status

## Dynamic DNS / Heartbeat

Provide editable fields:

```text
Enabled
AWS heartbeat URL
Heartbeat secret/token
Interval in minutes
Machine name
Route53 hostname, informational
```

Example:

```text
Enabled:             yes
Heartbeat URL:       https://xxxx.lambda-url.eu-central-1.on.aws/
Machine name:        home-pc
Interval:            15 minutes
Hostname:            home.opusmagus.com
```

The secret/token field should display masked.

Do not return the stored secret to the browser after it has been saved. Show only something such as:

```text
•••••••• configured
```

Allow replacing it with a new value.

---

# 5. Configuration Storage

Use a small JSON configuration file for normal settings.

Example:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 7860
  },
  "heartbeat": {
    "enabled": true,
    "url": "",
    "interval_minutes": 15,
    "machine_name": "home-pc",
    "route53_hostname": "home.opusmagus.com"
  },
  "actions": []
}
```

Secrets should not be placed directly in this normal JSON file if avoidable.

For Windows, prefer one of:

1. environment variable
2. Windows Credential Manager
3. Windows DPAPI-encrypted local secret

For the first implementation, environment variables are acceptable.

Keep this simple.

---

# 6. Heartbeat Daemon

The same Python application should run a lightweight background heartbeat loop.

Do not create a second complex service unless necessary.

Behavior:

1. Start with the web application.
2. On startup, if heartbeat is enabled, send a heartbeat shortly after startup.
3. Then send every configured interval, default 15 minutes.
4. Re-read configuration after it changes through the UI.
5. If public IP has not changed, still allow a heartbeat, but do not spam AWS unnecessarily.
6. Retry failures using basic bounded backoff.
7. Never stop the web server because AWS is unavailable.

Suggested heartbeat payload:

```json
{
  "machine": "home-pc",
  "timestamp": "2026-09-03T07:30:00+02:00",
  "local_ip": "192.168.1.101"
}
```

Do NOT trust a public IP supplied by the PC for DNS updates.

The AWS Lambda should determine the public IPv4 from the incoming HTTP request source IP.

Authentication header:

```text
Authorization: Bearer <heartbeat-secret>
```

The daemon only needs to know:

- heartbeat URL
- secret
- machine identifier

---

# 7. AWS Side

Create an optional `/aws` folder with minimal deployable AWS code.

Suggested architecture:

```text
Home PC
   |
   | HTTPS heartbeat
   v
Lambda Function URL
   |
   | validate bearer secret
   | determine caller public IP
   | compare Route53 record
   v
Route 53
home.opusmagus.com -> current public IPv4
```

Prefer Lambda Function URL over API Gateway for this tiny use case unless there is a compelling reason otherwise.

Lambda responsibilities:

1. Accept POST only.
2. Validate shared secret.
3. Extract source IP from the Lambda Function URL request context.
4. Validate that it is a public IPv4.
5. Read current Route 53 `A` record.
6. If IP differs, UPSERT it.
7. TTL around 60 seconds.
8. Return JSON status.

Example:

```json
{
  "ok": true,
  "ip": "89.150.157.33",
  "changed": true,
  "hostname": "home.opusmagus.com"
}
```

If unchanged:

```json
{
  "ok": true,
  "ip": "89.150.157.33",
  "changed": false
}
```

IAM for Lambda must be scoped as narrowly as practical to the specific hosted zone and record.

Do not give the home PC AWS credentials.

---

# 8. Lambda Configuration

Lambda environment variables:

```text
HEARTBEAT_SECRET=...
HOSTED_ZONE_ID=...
RECORD_NAME=home.opusmagus.com
TTL=60
```

The secret should ideally come from AWS Secrets Manager eventually.

For initial testing, a Lambda environment variable is acceptable, but clearly note in README how to move it to Secrets Manager.

---

# 9. Health Endpoints

Add:

```text
GET /health
```

Unauthenticated response:

```json
{"ok": true}
```

Do not expose machine details there.

Authenticated:

```text
GET /api/status
```

can return the richer status.

---

# 10. Logging

Log locally:

- startup
- login success/failure without passwords
- action invocation
- action result
- config change
- heartbeat success/failure
- IP change reported by AWS

Example:

```text
2026-09-03 07:31:22 heartbeat success ip=89.150.157.33 changed=false
```

Rotate logs so the daemon cannot fill the disk.

---

# 11. Windows Startup

Provide a simple way to run this automatically on Windows startup.

Prefer documenting two options:

### Simple

Windows Task Scheduler:

```text
python D:\github\little-daemon\app.py
```

Run whether user is logged in or not.

### Better later

Optional Windows Service wrapper.

Do not require a Windows Service for v1.

---

# 12. HTTPS

The current external test uses:

```text
http://89.150.157.33:7860
```

This is fine only for the immediate connectivity test.

Password authentication must NOT be considered production-safe over plain HTTP.

For the actual exposed control panel, implement or document an HTTPS path before using it regularly.

Preferred future options:

- reverse proxy with Caddy
- Cloudflare Tunnel
- Tailscale
- WireGuard/VPN
- HTTPS reverse proxy with proper certificate

Do not expose reusable login credentials over plaintext HTTP.

The DDNS heartbeat itself must use HTTPS.

---

# 13. Initial UI Style

Keep it extremely simple:

- dark background
- one centered dashboard
- small cards
- no gradients
- no animations
- no large JS framework
- mobile friendly
- clear green/red status markers
- one page

Do not spend significant time on styling.

Functionality first.

---

# 14. API

Suggested routes:

```text
GET  /health

GET  /login
POST /login
POST /logout

GET  /
GET  /api/status

GET  /api/config
POST /api/config/heartbeat

GET  /api/actions
POST /api/actions/{action_id}

POST /api/heartbeat/test
```

`/api/heartbeat/test` should immediately call the configured AWS heartbeat URL and return the result.

This is useful from the UI as a:

```text
[Test AWS Heartbeat]
```

button.

---

# 15. First Milestone

Implement this in small stages.

### Stage 1

- FastAPI conversion
- login/password protection
- dashboard
- current machine/public IP status

### Stage 2

- allowlisted local actions
- action execution UI
- logs

### Stage 3

- heartbeat configuration UI
- background heartbeat loop
- manual test button

### Stage 4

- AWS Lambda Function URL
- Route 53 update
- test `home.opusmagus.com`

### Stage 5

- Windows startup instructions
- tighten security
- README

Do not over-engineer beyond these requirements.

---

# 16. Acceptance Criteria

The implementation is complete when:

1. `python app.py` starts the service on `0.0.0.0:7860`.
2. Visiting the page requires authentication.
3. Passwords are never stored in plaintext.
4. The dashboard displays PC and heartbeat status.
5. The owner can trigger explicitly allowlisted PC actions.
6. Arbitrary browser-supplied shell commands are impossible.
7. Heartbeat settings can be edited in the UI.
8. A heartbeat can be manually tested.
9. The background task calls the AWS endpoint periodically.
10. Lambda detects the request's public IPv4.
11. Lambda updates `home.opusmagus.com` in Route 53 only when needed.
12. AWS credentials are never stored on the home PC.
13. Failure of AWS connectivity does not stop the local web server.
14. README contains exact setup and test commands.

---

# 17. Keep It Small

This project should feel like a utility, not a platform.

Target roughly:

- a few Python files
- a few hundred lines, not thousands
- minimal dependencies
- transparent behavior
- easy for one person to understand and maintain

If a simpler implementation meets the requirements safely, choose the simpler implementation.


All installs must be to local .venv venv folder