$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$envFile = Join-Path $PSScriptRoot ".env"

function Import-LocalEnv($path) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    foreach ($line in Get-Content -LiteralPath $path) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notlike "*=*") { continue }
        $name, $value = $line.Split("=", 2)
        if ($name -match "^[A-Za-z_][A-Za-z0-9_]*$") {
            $value = $value.Trim()
            if ($value.Length -ge 2 -and (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"')))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            Set-Item "Env:$($name.Trim())" $value
        }
    }
}

function Save-LocalEnv($path) {
    $lines = @(
        "ADMIN_USERNAME=$env:ADMIN_USERNAME",
        "ADMIN_PASSWORD_HASH=$env:ADMIN_PASSWORD_HASH",
        "SESSION_SECRET=$env:SESSION_SECRET",
        "HOST=$env:HOST",
        "PORT=$env:PORT",
        "PUBLIC_IP_URL=$env:PUBLIC_IP_URL",
        "SESSION_HOURS=$env:SESSION_HOURS"
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, (($lines -join [Environment]::NewLine) + [Environment]::NewLine), $utf8NoBom)
}

Import-LocalEnv $envFile

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { & $py.Source -3 -m venv .venv }
    else { & python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
}

& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install Python dependencies." }

if (-not $env:ADMIN_USERNAME) { $env:ADMIN_USERNAME = "admin" }
if (-not $env:ADMIN_PASSWORD_HASH) {
    Write-Host "No saved password found. Choose one now."
    $env:ADMIN_PASSWORD_HASH = (& $venvPython app.py --hash-password | Select-Object -Last 1).Trim()
    if (-not $env:ADMIN_PASSWORD_HASH) { throw "Could not create the password hash." }
}
if (-not $env:SESSION_SECRET) {
    $env:SESSION_SECRET = (& $venvPython -c "import secrets; print(secrets.token_urlsafe(32))").Trim()
}
if (-not $env:HOST) { $env:HOST = "0.0.0.0" }
if (-not $env:PORT) { $env:PORT = "7860" }
if (-not $env:PUBLIC_IP_URL) { $env:PUBLIC_IP_URL = "https://api.ipify.org" }
if (-not $env:SESSION_HOURS) { $env:SESSION_HOURS = "12" }

Save-LocalEnv $envFile
Write-Host "Saved settings to .env (password hash only, not the password)." -ForegroundColor DarkGray

Write-Host "Starting Little Daemon at http://localhost:7860" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop it."
& $venvPython app.py
