"""One clock: stored timestamps must reach text in local time.

Database rows are naive UTC (``TimestampMixin`` writes
``datetime.now(timezone.utc)`` into a ``DateTime(timezone=False)`` column)
while logs, users and the system-reminder block speak local time. A prompt that
mixes the two showed the same conversation as ``11:24:45`` and ``03:25:40`` at
once, which is exactly the sort of contradiction a model resolves by inventing
a story. These cases pin the conversion, not the formatting style.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from astrbot.core.utils.datetime_utils import to_local_display


def _local_offset() -> timedelta:
    return datetime.now().astimezone().utcoffset() or timedelta(0)


def test_naive_datetime_is_read_as_utc() -> None:
    naive_utc = datetime(2026, 11, 2, 3, 58, 17)
    expected = naive_utc.replace(tzinfo=timezone.utc).astimezone()
    assert to_local_display(naive_utc) == expected.strftime("%Y-%m-%d %H:%M:%S")


def test_aware_datetime_keeps_its_instant() -> None:
    aware = datetime(2026, 11, 2, 11, 58, 17, tzinfo=timezone(timedelta(hours=8)))
    assert to_local_display(aware) == to_local_display(aware.astimezone(timezone.utc))


def test_iso_string_with_z_suffix() -> None:
    assert to_local_display("2026-11-02T03:58:17Z") == to_local_display(
        datetime(2026, 11, 2, 3, 58, 17, tzinfo=timezone.utc)
    )


def test_string_form_of_a_naive_row() -> None:
    """``str(row.created_at)`` is how the history readers pass the value."""
    row_like = "2026-11-02 03:58:17.984712"
    assert to_local_display(row_like).startswith("2026-11-02 ")
    assert len(to_local_display(row_like)) == len("2026-11-02 11:58:17")


def test_epoch_seconds() -> None:
    stamp = datetime(2026, 11, 2, 3, 58, 17, tzinfo=timezone.utc).timestamp()
    assert to_local_display(int(stamp)) == to_local_display(
        datetime(2026, 11, 2, 3, 58, 17, tzinfo=timezone.utc)
    )


def test_minute_precision() -> None:
    value = datetime(2026, 11, 2, 3, 58, 17)
    assert to_local_display(value, with_seconds=False).count(":") == 1


def test_time_only_shape() -> None:
    """Per-line chat renderings need HH:MM:SS, not a sliced date string."""
    rendered = to_local_display(datetime(2026, 11, 2, 3, 58, 17), with_date=False)
    assert len(rendered) == len("11:58:17")
    assert rendered.count(":") == 2
    assert " " not in rendered


def test_empty_values_render_empty() -> None:
    assert to_local_display(None) == ""
    assert to_local_display("") == ""
    assert to_local_display("   ") == ""


def test_unparsable_text_is_returned_unchanged() -> None:
    """A caller still gets readable text instead of an exception mid-prompt."""
    assert to_local_display("not-a-time") == "not-a-time"


@pytest.mark.skipif(_local_offset() == timedelta(0), reason="host runs in UTC")
def test_offset_is_actually_applied() -> None:
    naive_utc = datetime(2026, 11, 2, 3, 58, 17)
    assert to_local_display(naive_utc) != naive_utc.strftime("%Y-%m-%d %H:%M:%S")
