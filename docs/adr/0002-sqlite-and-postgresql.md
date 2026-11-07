# ADR 0002 — SQLite for development, PostgreSQL for production

Development uses one SQLite file in WAL mode so a single worker and the API can share it. Production configuration rejects a SQLite URL.

Leases, the outbox, and optimistic versions are written so the same statements work on PostgreSQL. PostgreSQL-specific audit triggers are in the initial migration and still need a run against a real server.
