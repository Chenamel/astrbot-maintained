import uuid
from datetime import datetime, timezone


def generate_timestamp_id() -> str:
    """Generate a compact timestamp-based identifier.

    Returns:
        The local time in ``YYYYMMDDHHMMSSmmm`` format followed by four random
        hexadecimal characters.
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
    return f"{timestamp}_{uuid.uuid4().hex[:4]}"


def normalize_datetime_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime values to UTC.

    Naive datetimes are interpreted as UTC to match SQLite storage behavior.
    """
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_utc_isoformat(dt: datetime | None) -> str | None:
    normalized = normalize_datetime_utc(dt)
    if normalized is None:
        return None
    return normalized.isoformat()


def to_utc_timestamp(dt: datetime | None) -> float | None:
    normalized = normalize_datetime_utc(dt)
    if normalized is None:
        return None
    return normalized.timestamp()


def to_local_display(
    value: object, *, with_seconds: bool = True, with_date: bool = True
) -> str:
    """Render a stored timestamp in local time.

    Database rows store naive UTC (``TimestampMixin`` uses
    ``datetime.now(timezone.utc)`` with ``DateTime(timezone=False)``), while
    logs, users and the system-reminder block speak local time. Anything that
    puts a stored timestamp into text a person or a model reads has to come
    through here, otherwise one prompt carries two clocks that disagree by the
    UTC offset.

    Args:
        value: A datetime (naive values are treated as UTC), an ISO-8601
            string, or an epoch number in seconds.
        with_seconds: Whether the rendered string includes seconds.
        with_date: Whether the rendered string includes the date. False yields
            ``HH:MM:SS``, which is what per-line chat renderings need.

    Returns:
        The local-time string, or the original text when the value cannot be
        parsed. Never raises: callers put this into prompts and logs, where a
        crash would be worse than an unformatted timestamp.
    """
    if with_date:
        fmt = "%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M"
    else:
        fmt = "%H:%M:%S" if with_seconds else "%H:%M"

    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, datetime):
        normalized = normalize_datetime_utc(value)
        if normalized is None:
            return str(value)
        return normalized.astimezone().strftime(fmt)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).strftime(fmt)
        except (OverflowError, OSError, ValueError):
            return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        candidate = text.replace("Z", "+00:00") if text.endswith("Z") else text
        try:
            return to_local_display(
                datetime.fromisoformat(candidate),
                with_seconds=with_seconds,
                with_date=with_date,
            )
        except ValueError:
            pass
        try:
            return to_local_display(
                float(text), with_seconds=with_seconds, with_date=with_date
            )
        except ValueError:
            return value
    return str(value)
