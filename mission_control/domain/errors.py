"""Failures a caller can show to an engineer or a flight director."""


class AppError(Exception):
    """A failure with a message that is safe to show in the console."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidReport(AppError):
    """The filed report is missing a field or a reading is not a real number."""


class ModelCallError(AppError):
    """Microsoft Foundry did not return a usable completion."""


class ModelOutputError(AppError):
    """A completion arrived, and it did not match the schema this step requires."""


class ReportNotFound(AppError):
    """No saved report has this id."""


class AlreadyApproved(AppError):
    """A person already approved this briefing."""


class FoundryConfigError(AppError):
    """Foundry settings are missing or not a URL this client can call."""
