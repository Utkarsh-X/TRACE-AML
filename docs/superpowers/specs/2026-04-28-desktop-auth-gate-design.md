# TRACE-AML Desktop Auth Gate Design

## Goal

Add a desktop authorization layer for the Electron build so the packaged app only works for Google accounts explicitly allowed by the owner, and stops working when network validation or allowlist validation fails.

This design is intentionally stricter than a normal desktop sign-in flow:

- Google sign-in proves identity
- a remotely hosted allowlist decides access
- the local backend enforces access on every protected request
- the desktop app does not work offline once auth is enabled

## Scope

This design applies to the Electron desktop flow and the local FastAPI backend it launches.

It does not attempt to solve:

- enterprise SSO
- multi-role permissions
- long-lived offline sessions
- distributed central session storage

## Chosen Approach

The desktop app will use four layers together:

1. Google Identity Services sign-in in a dedicated auth page
2. Backend verification of the Google ID token
3. Backend allowlist validation against a remote JSON policy URL under owner control
4. Short-lived in-memory local sessions that are continuously revalidated

This is preferred over a frontend-only Google sign-in because the backend remains the real authority. It is also preferred over a bundled local allowlist because the owner needs remote revocation across copies already installed on other machines.

## Remote Authority Model

The source of truth for access is a remote JSON document fetched over HTTPS.

Recommended host:

- GitHub raw URL
- public gist raw URL

Minimum policy shape:

```json
{
  "version": 1,
  "allowed_emails": [
    "owner@example.com",
    "tester@example.com"
  ],
  "message": "Access is restricted to approved accounts."
}
```

Behavior:

- if the signed-in Google email is present, access may continue
- if it is missing, the session is denied or revoked
- if the policy URL cannot be fetched, access is denied while auth is enabled

This fail-closed behavior is required because the user wants the desktop app to stop working without online validation.

## User Flow

Desktop launch flow becomes:

1. Electron splash loads
2. local backend starts and answers `/health`
3. Electron opens `/ui/auth/index.html`
4. auth page checks `/api/v1/auth/config`
5. if auth is disabled, auth page immediately redirects to Live Ops
6. if auth is enabled:
   - page checks current backend session
   - if already valid, redirect to Live Ops
   - otherwise render Google sign-in button
7. user signs in with Google
8. frontend posts the Google credential to backend
9. backend verifies Google token, fetches policy, checks allowlist, creates short session
10. frontend redirects to Live Ops

While the app is open:

- frontend heartbeats session validity periodically
- backend revalidates sessions against the remote allowlist
- if validation fails, UI is redirected back to auth and protected API calls stop working

## Backend Design

New backend auth components:

- `AuthSettings`: auth configuration block in main settings
- `GoogleIdentityVerifier`: validates Google ID tokens
- `RemoteAuthPolicyClient`: fetches and parses the remote allowlist JSON
- `DesktopSessionManager`: owns short-lived in-memory desktop sessions

Protected backend endpoints:

- all `/api/v1/*` endpoints except `/api/v1/auth/*`

Public endpoints:

- `/`
- `/health`
- `/api/v1/auth/config`
- `/api/v1/auth/google`
- `/api/v1/auth/session`
- `/api/v1/auth/logout`

Public UI paths:

- `/ui/auth/*`
- shared assets needed by the auth page

Protected UI paths:

- all app pages such as Live Ops, Settings, Entities, Enrollment, History, Database, About

If a protected UI page is requested without a valid session, the backend redirects to the auth page instead of serving the target page.

## Session Model

Sessions are local and in-memory, not persisted to disk.

Session properties:

- random opaque session id stored in an `HttpOnly` cookie
- short expiration window
- owner email, display name, avatar URL
- last successful allowlist validation timestamp

Validation rules:

- expired session: reject
- missing remote validation within configured interval: revalidate now
- failed revalidation: revoke session and reject
- offline / policy fetch failure while auth is enabled: reject

This design intentionally forces fresh online validation instead of keeping stale local authorization.

## Frontend Design

New frontend page:

- `src/frontend/auth/index.html`

New shared script:

- `src/frontend/shared/trace_auth.js`

Responsibilities:

- render auth UI
- load Google Identity Services
- submit Google credential to backend
- redirect authenticated users to Live Ops
- heartbeat session validity on protected pages
- redirect protected pages back to auth if session becomes invalid

The existing `desktop_shell.js` remains responsible for desktop shell controls like exit, and will invoke the shared auth guard on protected pages.

## Electron Design

Electron does not become the security authority. It only changes startup flow:

- splash remains first
- auth page becomes the first backend-served page
- Live Ops is opened only after backend health and auth-page navigation

Electron packaged mode continues to include `.env`, so auth settings can be supplied without hardcoding secrets into the UI source.

## Configuration

New settings block:

```yaml
auth:
  enabled: false
  google_client_id: ""
  policy_url: ""
  session_ttl_minutes: 15
  validation_interval_seconds: 60
  request_timeout_seconds: 8
```

Expected environment overrides:

- `TRACE_AML_AUTH__ENABLED`
- `TRACE_AML_AUTH__GOOGLE_CLIENT_ID`
- `TRACE_AML_AUTH__POLICY_URL`
- `TRACE_AML_AUTH__SESSION_TTL_MINUTES`
- `TRACE_AML_AUTH__VALIDATION_INTERVAL_SECONDS`
- `TRACE_AML_AUTH__REQUEST_TIMEOUT_SECONDS`

Auth will remain opt-in by configuration because the repository does not contain the owner’s Google client ID or final policy URL.

## Failure Behavior

If auth is enabled:

- missing Google client ID: auth page shows misconfiguration state, app does not proceed
- missing policy URL: auth page shows misconfiguration state, app does not proceed
- Google sign-in failure: remain on auth page with retry state
- allowlist rejection: remain on auth page with explicit denial state
- remote policy fetch failure: session invalidates, app returns to auth page
- network loss after launch: session eventually invalidates and app returns to auth page

## Testing Strategy

Backend tests:

- config loading for auth settings
- protected API returns `401` without session when auth is enabled
- protected UI redirects to auth page without session
- successful sign-in path creates session cookie when verifier and policy allow the user
- revoked / removed user loses access on next validation cycle

Frontend tests:

- auth config bootstrap states
- protected-page auth guard redirects on invalid session

Smoke expectation:

- Electron splash -> auth page -> Google sign-in -> Live Ops
- removing a user from the remote policy causes the installed app to lose access after the next validation

## Open External Requirement

The implementation can be completed without asking further repo questions, but a fully usable secured desktop build still requires the owner to provide:

- a Google OAuth / Google Identity Services client ID authorized for the desktop app’s local origin
- a remote JSON policy URL they control

Without those two values, the feature can compile but cannot complete real sign-in.
