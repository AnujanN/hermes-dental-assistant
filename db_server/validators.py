"""
Validation utilities for the db_server package.

All input validation logic for database operations is centralised here,
keeping the data-access functions in db_manager.py and qdrant_manager.py
focused on their single responsibility.
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when an input fails validation."""
    pass


# ---------------------------------------------------------------------------
# Phone number
# ---------------------------------------------------------------------------

def validate_phone_number(phone_number: str) -> str:
    """
    Validate and normalise a phone number.

    Returns the stripped value on success.
    Raises ``ValidationError`` if the value is empty or None.
    """
    if not phone_number or not str(phone_number).strip():
        raise ValidationError("Phone number is required and cannot be empty.")
    cleaned = str(phone_number).strip()
    logger.debug("Validated phone number: %s", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Patient name
# ---------------------------------------------------------------------------

def validate_patient_name(name: str) -> str:
    """
    Validate a patient name string.

    Returns the stripped value on success.
    Raises ``ValidationError`` if empty or obviously invalid.
    """
    if not name or not str(name).strip():
        raise ValidationError("Patient name is required and cannot be empty.")
    cleaned = str(name).strip()
    if len(cleaned) < 2:
        raise ValidationError(
            f"Patient name '{cleaned}' is too short — at least 2 characters required."
        )
    logger.debug("Validated patient name: %s", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Date / time formats
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def validate_date_format(date_str: str) -> str:
    """
    Validate that *date_str* follows ``YYYY-MM-DD`` and represents a real
    calendar date.

    Returns the stripped value on success.
    Raises ``ValidationError`` on bad format or invalid date.
    """
    if not date_str or not str(date_str).strip():
        raise ValidationError("Date is required and cannot be empty.")
    cleaned = str(date_str).strip()

    if not _DATE_RE.match(cleaned):
        raise ValidationError(
            f"Date '{cleaned}' must be in YYYY-MM-DD format (e.g. '2026-07-20')."
        )
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(
            f"Date '{cleaned}' is not a valid calendar date."
        )
    logger.debug("Validated date: %s", cleaned)
    return cleaned


def validate_time_format(time_str: str) -> str:
    """
    Validate that *time_str* follows ``HH:MM`` in 24-hour format.

    Returns the stripped value on success.
    Raises ``ValidationError`` on bad format or out-of-range values.
    """
    if not time_str or not str(time_str).strip():
        raise ValidationError("Time is required and cannot be empty.")
    cleaned = str(time_str).strip()

    if not _TIME_RE.match(cleaned):
        raise ValidationError(
            f"Time '{cleaned}' must be in HH:MM 24-hour format (e.g. '09:00')."
        )
    hour, minute = map(int, cleaned.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValidationError(
            f"Time '{cleaned}' contains out-of-range hour/minute values."
        )
    logger.debug("Validated time: %s", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Call-log helpers
# ---------------------------------------------------------------------------

def validate_log_id(log_id) -> int:
    """
    Validate that *log_id* is a positive integer.

    Returns the integer value on success.
    Raises ``ValidationError`` otherwise.
    """
    try:
        value = int(log_id)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Log ID must be a positive integer, got '{log_id}'."
        )
    if value <= 0:
        raise ValidationError(
            f"Log ID must be a positive integer, got {value}."
        )
    logger.debug("Validated log_id: %d", value)
    return value


def validate_duration(duration_seconds) -> int:
    """
    Validate that *duration_seconds* is a non-negative integer.

    Returns the integer value on success.
    Raises ``ValidationError`` otherwise.
    """
    try:
        value = int(duration_seconds)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Duration must be a non-negative integer, got '{duration_seconds}'."
        )
    if value < 0:
        raise ValidationError(
            f"Duration must be non-negative, got {value}."
        )
    logger.debug("Validated duration: %d seconds", value)
    return value
