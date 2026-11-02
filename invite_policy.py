"""Minimum notice for Barbara's new invitations, measured in Central Time."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def earliest_invite_start(now=None):
    cutoff = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/Chicago"))
    remaining = 3
    while remaining:
        cutoff += timedelta(days=1)
        if cutoff.weekday() < 5:
            remaining -= 1
    return cutoff
