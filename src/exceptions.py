from fastapi import HTTPException


class AppException(HTTPException):
    """Structured application exception returning {"detail": ..., "code": ...}."""

    def __init__(self, status_code: int, message: str, code: str):
        super().__init__(
            status_code=status_code,
            detail={"detail": message, "code": code},
        )
