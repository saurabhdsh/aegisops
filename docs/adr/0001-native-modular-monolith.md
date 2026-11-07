# ADR 0001 — Modular monolith, native processes

AegisOps runs as an API process and a worker process in a virtualenv. Workflow state is in the database. Docker, Compose, Kubernetes, Helm, Redis, and Celery are out of scope.

The cost is that horizontal scale depends on PostgreSQL row locking rather than a broker. That is acceptable until measurement says otherwise.
