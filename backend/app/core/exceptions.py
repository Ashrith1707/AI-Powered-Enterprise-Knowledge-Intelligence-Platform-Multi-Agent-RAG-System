"""Domain exceptions mapped to HTTP responses in main.py."""


class AppError(Exception):
    status_code = 500

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ValidationError(AppError):
    status_code = 400


class NotFoundError(AppError):
    status_code = 404


class ProcessingError(AppError):
    status_code = 422


class LLMNotConfiguredError(AppError):
    status_code = 503
