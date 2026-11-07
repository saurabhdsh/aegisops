"""Application errors with stable API codes."""

from __future__ import annotations


class AegisError(Exception):
    """Error that maps to the public error contract."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AegisError):
    def __init__(self, message: str = "Resource not found", details: dict | None = None) -> None:
        super().__init__("not_found", message, 404, details)


class UnauthorizedError(AegisError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__("unauthorized", message, 401)


class ForbiddenError(AegisError):
    def __init__(self, message: str = "Forbidden", details: dict | None = None) -> None:
        super().__init__("forbidden", message, 403, details)


class ConflictError(AegisError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("conflict", message, 409, details)


class IntegrationError(AegisError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("integration_error", message, 502, details)


class NotImplementedYet(AegisError):
    def __init__(self, message: str) -> None:
        super().__init__("not_implemented", message, 501)


class AuditImmutableError(AegisError):
    def __init__(self) -> None:
        super().__init__("audit_immutable", "Audit events are append-only", 409)
