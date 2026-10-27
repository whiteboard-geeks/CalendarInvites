from datetime import datetime, timedelta, timezone

import pytest

from bridge import proposals

COUNTER = """BEGIN:VCALENDAR\r
METHOD:COUNTER\r
BEGIN:VTIMEZONE\r
TZID:Central Standard Time\r
END:VTIMEZONE\r
BEGIN:VEVENT\r
ATTENDEE;PARTSTAT=TENTATIVE;CN=Adam:mailto:Adam@example.test\r
UID:abc@google.com\r
DTSTART;TZID=Central Standard Time:20351112T153000\r
DTEND;TZID=Central Standard Time:20351112T160000\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_outlook_counter_ics_parses_windows_zone_to_utc():
    assert proposals.ics_counters(COUNTER) == [{"uid": "abc@google.com", "from": "adam@example.test",
        "start": "2035-11-12T21:30:00+00:00", "end": "2035-11-12T22:00:00+00:00"}]
    assert proposals.ics_counters(COUNTER.replace("METHOD:COUNTER", "METHOD:REPLY")) == []
    utc = COUNTER.replace(";TZID=Central Standard Time:20351112T153000", ":20351112T213000Z")
    assert proposals.ics_counters(utc)[0]["start"] == "2035-11-12T21:30:00+00:00"
