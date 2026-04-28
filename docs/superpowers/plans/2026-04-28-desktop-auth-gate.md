# TRACE-AML Desktop Auth Gate Implementation Plan

## Objective

Implement an online-only desktop auth gate for the Electron build using Google sign-in plus a remotely controlled allowlist, with backend-enforced short-lived sessions and continuous revocation checks.

## Assumptions

- desktop auth remains opt-in through config / env
- packaged builds already include `.env`
- the owner will later supply a real Google client ID and remote allowlist URL
- current browser/dev mode may remain usable with auth disabled

## Work Plan

1. Add configuration and auth core primitives
   - add `AuthSettings` to `trace_aml.core.config`
   - add auth core modules for:
     - Google identity verification
     - remote allowlist policy fetch
     - in-memory desktop session management
   - add a small public user/session model for auth responses

2. Add backend auth endpoints and enforcement
   - add `/api/v1/auth/config`
   - add `/api/v1/auth/google`
   - add `/api/v1/auth/session`
   - add `/api/v1/auth/logout`
   - add middleware that:
     - protects `/api/v1/*` except auth endpoints
     - redirects protected `/ui/*` pages to auth when no valid session exists
   - tighten CORS behavior when auth is enabled

3. Add frontend auth flow
   - create `src/frontend/auth/index.html`
   - create `src/frontend/shared/trace_auth.js`
   - render Google sign-in button and error states
   - redirect successful sessions into Live Ops
   - add heartbeat-based session validation on protected pages

4. Wire Electron startup to the auth page
   - change the initial backend-served page from Live Ops to Auth
   - keep splash behavior intact
   - use desktop config for Electron dev startup so auth flow can be exercised in Electron mode

5. Update packaged configuration and samples
   - add auth block to desktop/demo config files
   - add a sample allowlist JSON document
   - add build notes for Google client ID and policy URL configuration

6. Verify behavior
   - add backend tests first
   - run focused pytest coverage for config + service auth
   - run Electron runtime tests
   - smoke the browser flow with auth disabled to confirm non-auth builds still work

## Sequencing

Implementation will follow TDD:

1. failing config + service auth tests
2. backend auth implementation
3. frontend auth page and guards
4. Electron startup wiring
5. verification

## Risks To Watch

- protected UI middleware accidentally blocking auth assets
- session heartbeat fighting with existing connection-state overlay logic
- packaged builds using the wrong config file in Electron dev mode
- Google client ID not yet available, preventing a real end-to-end sign-in smoke test

## Done Criteria

- protected desktop pages cannot be used without a valid backend session when auth is enabled
- allowed Google account can start a session
- non-allowlisted account is denied
- removing an account from the remote policy invalidates access on the next validation cycle
- offline / policy fetch failure invalidates access while auth is enabled
- auth-disabled builds still load normally
