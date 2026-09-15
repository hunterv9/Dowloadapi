"""Typed platform errors — replaces bare ``raise Exception`` in API clients.

Lets ``core.service.friendly_error`` catch by type instead of
string-matching Vietnamese messages.
"""

__all__ = [
    "PlatformError",
    "AuthError",
    "NotFoundError",
    "RateLimitError",
    "ValidationError",
]


class PlatformError(Exception):
    """Base for all TikTok/Douyin platform failures."""

    def __init__(self, message: str = "", status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AuthError(PlatformError):
    """Auth/cookie failures (401/403, login required, private video)."""


class NotFoundError(PlatformError):
    """Video/profile not found (404, removed, unparseable stream)."""


class RateLimitError(PlatformError):
    """Rate limiting (HTTP 429)."""


class ValidationError(PlatformError):
    """Bad input (bad URL, unrecognised video ID)."""
