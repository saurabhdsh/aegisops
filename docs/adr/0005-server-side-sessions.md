# ADR 0005 — Sessions are hashed and server-side

Login returns a signed token and stores only its SHA-256. Logout revokes the row. Cookie sessions require a CSRF header because browsers attach cookies automatically. Bearer calls still require a live session row, so a signature alone is not enough.

An extra `auth_sessions` table is not in the original table list. It exists so sessions can be revoked. `operational_controls` exists so the emergency stop is durable.
