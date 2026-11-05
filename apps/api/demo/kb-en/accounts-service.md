# Accounts service (identity and sessions)

Accounts manages who each user is, what role they sign in with and how long their session lasts. The
Accounts team maintains it, and the technical owner appears in the [team map](team-map.md).

## How a session works

- On sign-in, Accounts creates a session and returns an opaque token in an `httpOnly` cookie. The
  token holds no user data: it is only resolved in the database.
- The session expires after 30 days of inactivity. Each use renews it (sliding expiration).
- A user can revoke all their sessions. An administrator can also revoke another user's sessions, with an audit record.

## Passwords and brute force

- Passwords are stored with Argon2id. They are never stored in the clear or written to logs.
- After 5 failed attempts in 15 minutes, sign-in is blocked for that email and for that IP
  (a 429 response with `Retry-After`).

## Roles

- **regular:** uses the application.
- **admin:** also accesses the admin panel. The last active administrator cannot deactivate themselves.

## For other services

Services do not check passwords: they ask Accounts to validate the session token at the gateway and
receive the user and their role. Single sign-on (SSO) is being studied and does not have an ADR yet.

## Test access

To ask for a test account, write in #accounts-help with your name and the environment. Never share
passwords in the channel: the Accounts team generates them and hands them over privately.
