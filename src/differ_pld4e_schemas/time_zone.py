"""
The lab's time zone, in which runs and steps are logged.

The lab notes clock times (hh:mm) as its clocks and system logs show them. They
are turned into instants with the lab's time zone, which knows the clock
change: 09:00 on a winter day is +01:00 in Amsterdam, on a summer day +02:00.
NOMAD stores datetimes in UTC, so they are turned back into the lab's clock
time to be shown, compared or used in a sample ID. Neither the browser's time
zone nor the offset of a stored datetime decides this, so a logbook reads the
same wherever and whenever it is opened.

The zone is set in nomad.yaml (default Europe/Amsterdam)::

    plugins:
      entry_points:
        options:
          differ_pld4e_schemas.schema_packages:schema_package_entry_point:
            lab_time_zone: Europe/Amsterdam
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_LAB_TIME_ZONE = 'Europe/Amsterdam'


def lab_time_zone_name() -> str:
    """The configured IANA name of the lab's time zone."""
    from differ_pld4e_schemas.database import ENTRY_POINT_ID

    try:
        from nomad.config import config

        entry_point = config.get_plugin_entry_point(ENTRY_POINT_ID)
    except (AttributeError, KeyError, ImportError):  # plugins not loaded
        return DEFAULT_LAB_TIME_ZONE
    return getattr(entry_point, 'lab_time_zone', None) or DEFAULT_LAB_TIME_ZONE


def lab_zone() -> ZoneInfo:
    try:
        return ZoneInfo(lab_time_zone_name())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_LAB_TIME_ZONE)


def lab_wall_time(moment: datetime) -> datetime:
    """`moment` on the lab's clock. A naive datetime is taken as UTC, as NOMAD
    stores it."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(lab_zone())


def lab_instant(day: date, clock: time) -> datetime:
    """
    The instant at which the lab's clock showed `clock` on `day`. In the hour
    repeated when the clock goes back, the first one; a time skipped when the
    clock goes forward is taken as the offset before the change (see
    `is_skipped`).
    """
    return datetime.combine(day, clock, tzinfo=lab_zone())


def is_skipped(day: date, clock: time) -> bool:
    """Whether the lab's clock never showed `clock` on `day` (the hour skipped
    when it goes forward, e.g. 02:30 on the last Sunday of March)."""
    moment = lab_instant(day, clock)
    back = moment.astimezone(UTC).astimezone(lab_zone())
    return (back.hour, back.minute) != (clock.hour, clock.minute)
