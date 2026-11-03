# Little Daemon

Small authenticated FastAPI control panel for one Windows PC.

## Stage 1 setup

The easiest way to set up and run it is:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-and-run.ps1
```

The script installs dependencies, asks for the admin password on the first run, saves only its Argon2 hash and a session secret to the local git-ignored `.env` file, and starts the server. Later runs do not prompt again.

After the first setup, this also works:

```powershell
python app.py
```

It listens on `http://0.0.0.0:7860` by default. `/health` is public and returns only `{"ok":true}`; the dashboard and status API require login.

The Actions section runs only the built-ins listed in `data/config.json`. It includes confirmed restart and shutdown actions with a 30-second delay. You can add an explicit script path there; browser requests cannot submit arbitrary commands or arguments. The external HTTP URL is suitable only for initial connectivity testing. Do not send reusable credentials over plain HTTP. Put HTTPS or a VPN/reverse proxy in front before regular exposure.

## Tests

```powershell
python -m pytest
```

Allowlisted local actions and the AWS heartbeat are planned for the next stages.
