from bridge import proposals
from test_worker_postgres import linked, pair


class Mailer:
    def __init__(self):
        self.sent = []

    def reply(self, data, text):
        self.sent.append(text)


def propose(worker, meeting, hour=16):
    p = {"from": "lead@example.test", "start": f"2035-09-09T{hour}:00:00+00:00", "end": f"2035-09-09T{hour}:30:00+00:00"}
    proposals.record(worker.store, meeting["operation"], p)
    worker.process(meeting["operation"])
    return worker.store.get(meeting["operation"])


def answer(b, event_id, status, **fields):
    b.update(event_id, attendees=[{"email": "main@example.test", "responseStatus": status}], **fields)


def test_proposal_asks_barbara_once_and_yes_moves_meeting_and_her_copy(worker, command):
    worker.mailer = Mailer()
    meeting = linked(worker, command)
    o, b, oi, bi = pair(worker, meeting)
    meeting = propose(worker, meeting)
    event_id = meeting["data"]["proposal"]["event_id"]
    asked = b.events[event_id]
    assert asked["start"]["dateTime"] == "2035-09-09T16:00:00+00:00"
    assert asked["attendees"] == [{"email": "main@example.test", "responseStatus": "needsAction"}]
    assert asked["organizer"]["email"] == o.account["email"] and asked["privateCopy"] is True
    worker.process(meeting["operation"])  # no answer yet: nothing else happens
    proposals.record(worker.store, meeting["operation"], {"from": "lead@example.test",
        "start": "2035-09-09T16:00:00+00:00", "end": "2035-09-09T16:30:00+00:00"})  # same email seen again
    assert b.writes.count("import") == 2  # her copy + one proposal event
    answer(b, event_id, "accepted")
    worker.process(meeting["operation"])
    assert o.events[oi]["start"]["dateTime"] == "2035-09-09T16:00:00+00:00"
    assert b.events[bi]["start"] == o.events[oi]["start"]
    assert b.events[event_id]["status"] == "cancelled"
    assert worker.store.get(meeting["operation"])["data"]["proposals_done"][-1]["status"] == "accepted"
    assert worker.mailer.sent == []


def test_barbara_counters_by_moving_the_proposal_then_yes(worker, command):
    worker.mailer = Mailer()
    meeting = linked(worker, command)
    o, b, oi, bi = pair(worker, meeting)
    event_id = propose(worker, meeting)["data"]["proposal"]["event_id"]
    answer(b, event_id, "accepted", start={"dateTime": "2035-09-09T18:00:00+00:00", "timeZone": "UTC"},
           end={"dateTime": "2035-09-09T18:30:00+00:00", "timeZone": "UTC"})
    worker.process(meeting["operation"])
    assert o.events[oi]["start"]["dateTime"] == "2035-09-09T18:00:00+00:00"


def test_no_keeps_time_and_replies_once(worker, command):
    worker.mailer = Mailer()
    meeting = linked(worker, command)
    o, b, oi, bi = pair(worker, meeting)
    event_id = propose(worker, meeting)["data"]["proposal"]["event_id"]
    answer(b, event_id, "declined")
    worker.process(meeting["operation"])
    worker.process(meeting["operation"])
    assert o.events[oi]["start"]["dateTime"] == "2035-09-09T14:00:00+00:00"
    assert "time" not in o.writes
    assert len(worker.mailer.sent) == 1 and "doesn't work" in worker.mailer.sent[0]
    assert b.events[event_id]["status"] == "cancelled"


def test_new_proposal_replaces_open_one_and_cancellation_cleans_up(worker, command):
    worker.mailer = Mailer()
    meeting = linked(worker, command)
    o, b, oi, bi = pair(worker, meeting)
    first = propose(worker, meeting)["data"]["proposal"]["event_id"]
    second = propose(worker, meeting, 17)["data"]["proposal"]["event_id"]
    assert b.events[first]["status"] == "cancelled" and second != first
    o.update(oi, status="cancelled")
    worker.process(meeting["operation"])
    worker.process(meeting["operation"])
    assert b.events[second]["status"] == "cancelled"


def test_scan_records_microsoft_proposals_for_tentative_invitees(worker, command):
    meeting = linked(worker, command, "microsoft")
    o, b, oi, bi = pair(worker, meeting)
    o.update(oi, attendees=[{"email": "lead@example.test", "responseStatus": "tentative"}])
    worker.process(meeting["operation"])
    o.proposed = [{"from": "lead@example.test", "start": "2035-09-09T16:00:00+00:00", "end": "2035-09-09T16:30:00+00:00"}]
    proposals.scan(worker)
    assert worker.store.get(meeting["operation"])["data"]["proposal"]["status"] == "new"
