# TRACE-AML Desktop Build Guide

## Goal

Build a Windows Electron app that starts its own local backend without requiring a separate terminal window.

## Architecture

The desktop build is a two-stage package:

1. Build a standalone Python backend artifact from `.venv311`
2. Package that backend artifact into the Electron app

This is the supported path for future iterations. Do not bundle `.venv` or `.venv311` directly into Electron.

## Prerequisites

Use the working Python environment:

```powershell
cd "D:\github FORK\TRACE-ML"
.\.venv311\Scripts\python.exe -m pip install pytest pyinstaller
```

## Quick Verification

Before packaging, confirm the desktop-share config starts correctly:

```powershell
cd "D:\github FORK\TRACE-ML"
.\.venv311\Scripts\trace-aml.exe --config config/config.desktop.yaml service run --host 127.0.0.1 --port 18080
```

Then verify:

```powershell
Invoke-WebRequest http://127.0.0.1:18080/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:18080/api/v1/live/snapshot -UseBasicParsing
```

## Build Backend

```powershell
cd "D:\github FORK\TRACE-ML"
.\scripts\build_backend.ps1
```

Expected output:

```text
build\backend\trace_aml_backend\trace-aml-backend.exe
```

## Build Electron

```powershell
cd "D:\github FORK\TRACE-ML\electron"
npm install
npm test
npm run dist
```

`npm run dist` now calls the backend build script first, then runs `electron-builder`.

## Shareable Config

Packaged mode uses:

```text
config/config.desktop.yaml
```

That profile:
- keeps the current demo recognition tuning
- disables outbound email
- disables outbound WhatsApp
- disables PDF report generation
- keeps action logging enabled

## Optional Desktop Auth Gate

The desktop auth gate is implemented but remains config-driven.

To turn it on for a secured release build:

1. Create a Google Identity Services client ID
2. Add this origin in Google Cloud:

```text
http://127.0.0.1:18080
```

3. Host a remote allowlist JSON file over HTTPS
4. Set these values in `.env` before packaging:

```text
TRACE_AML_AUTH__ENABLED=true
TRACE_AML_AUTH__GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
TRACE_AML_AUTH__POLICY_URL=https://your-remote-policy-url/auth-policy.json
TRACE_AML_AUTH__SESSION_TTL_MINUTES=15
TRACE_AML_AUTH__VALIDATION_INTERVAL_SECONDS=60
```

5. Rebuild the desktop package

This repo now includes a concrete release policy file at:

```text
config/auth-policy.release.json
```

The packaged `.env` is configured to use the raw GitHub URL for that file:

```text
https://raw.githubusercontent.com/Utkarsh-X/TRACE-AML/main/config/auth-policy.release.json
```

Policy format example:

```json
{
  "version": 1,
  "allowed_emails": [
    "owner@example.com",
    "tester@example.com"
  ],
  "message": "Access is restricted to approved Google accounts."
}
```

With auth enabled:
- users must sign in with Google before opening the workspace
- only allowlisted accounts can continue
- the app fails closed if the remote policy cannot be fetched
- removing an email from the policy invalidates access on the next validation cycle

## Portable Data Behavior

Electron sets `TRACE_DATA_ROOT` before launching the backend, so packaged mode writes runtime data under the user-specific app-data directory instead of inside the install folder.

Important data categories:
- LanceDB vectors
- encrypted vault blobs and indexes
- screenshots
- logs
- exports

## Smoke Test After Build

Use the unpacked app first:

```powershell
cd "D:\github FORK\TRACE-ML\electron\dist\win-unpacked"
.\TRACE-AML.exe
```

Then verify:
- splash screen appears
- welcome screen appears
- main workspace loads
- `/health` responds on `127.0.0.1:18080`
- no manual backend terminal is required

## Current Blocking Requirement

If the build toolchain is missing, install these into `.venv311`:

```powershell
.\.venv311\Scripts\python.exe -m pip install pytest pyinstaller
```

Without `PyInstaller`, the Electron package cannot yet switch to the stable compiled-backend architecture.
