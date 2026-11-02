from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from invite_policy import earliest_invite_start
from test_legacy import function

@pytest.mark.parametrize('sent,expected', [
    ('2026-10-30T12:48:08-05:00', '2026-11-04T12:48:08-06:00'),
    ('2026-11-02T12:00:00-06:00', '2026-11-05T12:00:00-06:00'),
    ('2026-11-05T12:00:00-06:00', '2026-11-10T12:00:00-06:00'),
    ('2026-10-31T12:00:00-05:00', '2026-11-04T12:00:00-06:00'),
    ('2026-11-01T12:00:00-06:00', '2026-11-04T12:00:00-06:00'),
    ('2027-03-12T12:00:00-06:00', '2027-03-17T12:00:00-05:00'),
    ('2026-10-30T02:00:00+00:00', '2026-11-03T21:00:00-06:00'),
])
def test_three_business_days_preserve_central_time_across_weekends_and_dst(sent, expected):
    actual = earliest_invite_start(datetime.fromisoformat(sent))
    assert actual.isoformat() == expected
    assert actual.tzinfo == ZoneInfo('America/Chicago')

def test_legacy_barbara_boundary_other_consultants_unchanged():
    cutoff = datetime(2035, 1, 10, 12, tzinfo=timezone.utc)
    calendar = ['barbara.pigg@whiteboardgeeks.com']
    check = function('slot_has_notice', {
        'get_current_calendar_id': lambda: calendar[0],
        'earliest_invite_start': lambda: cutoff})
    assert not check(cutoff - timedelta(microseconds=1))
    assert check(cutoff)
    assert not check(datetime(2035, 1, 10))
    calendar[0] = 'april@whiteboardgeeks.com'
    assert check(cutoff - timedelta(days=1))


def test_legacy_send_guard_runs_before_calendar_mutation():
    import datetime as dt
    def forbidden():
        raise AssertionError("Calendar service must not be called")
    create = function('create_calendar_invite', {
        'slot_has_notice': lambda start: False, 'datetime': dt,
        'get_calendar_service': forbidden, 'HttpError': TypeError})
    with pytest.raises(ValueError, match='three business days'):
        create({}, '2035-01-01T12:00:00+00:00', '2035-01-01T12:30:00+00:00', 'Intro', 'Body')
