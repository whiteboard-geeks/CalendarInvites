from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import time

import pytest

from bridge.domain import Blocked


def reserve(store, command, task, capacity=100):
    try:
        return store.reserve(dict(command, task_id=task), lambda *_: ([], capacity))
    except Blocked as error:
        return str(error)


def test_concurrent_task_reservation_is_one_charge_and_one_sender(store, command):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(store, command, "task_same"), range(16)))
    assert len({r["sender"] for r in results}) == 1
    with store.connect() as c:
        assert c.execute("SELECT sum(used) AS n FROM bridge_caps").fetchone()["n"] == 1
        assert c.execute("SELECT cursor FROM bridge_rotation").fetchone()["cursor"] == 1
        assert c.execute("SELECT count(*) AS n FROM bridge_jobs").fetchone()["n"] == 1


def test_concurrent_slot_capacity_reservations(store, command):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda n: reserve(store, command, "task_" + str(n), 8), range(20)))
    assert sum(isinstance(r, dict) for r in results) == 8
    assert results.count("slot_at_capacity") == 12


def test_caps_under_concurrency_and_retry_does_not_charge(store, command):
    with store.connect() as c:
        c.execute("UPDATE bridge_senders SET account=jsonb_set(account,'{daily_cap}','1') WHERE id IN ('g1','g2')")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda n: reserve(store, command, "task_" + str(n)), range(10)))
    successes = [r for r in results if isinstance(r, dict)]
    assert len(successes) == 2
    assert {r["sender"] for r in successes} == {"g1", "g2"}
    original = successes[0]
    retry = reserve(store, dict(command, groups=["main"]), original["task_id"])
    assert retry["sender"] == original["sender"]
    with store.connect() as c:
        assert c.execute("SELECT sum(used) AS n FROM bridge_caps").fetchone()["n"] == 2


def test_reservation_rollback_on_unknown_calendar_capacity(store, command):
    def failed(*_):
        raise Blocked("provider_http_403")
    with pytest.raises(Blocked):
        store.reserve(command, failed)
    with store.connect() as c:
        assert c.execute("SELECT cursor FROM bridge_rotation").fetchone()["cursor"] == 0
        assert c.execute("SELECT count(*) AS n FROM bridge_meetings").fetchone()["n"] == 0


def test_close_recent_from_pins_sender_without_advancing_rotation(store, command):
    with store.connect() as c:
        email = c.execute("SELECT account->>'email' AS email FROM bridge_senders WHERE id='g2'").fetchone()["email"]
    first = store.reserve(dict(command, task_id="task_sticky", preferred_from=[email]), lambda *_: ([], 8))
    assert first["sender"] == "g2"
    with store.connect() as c:
        assert c.execute("SELECT cursor FROM bridge_rotation").fetchone()["cursor"] == 0
    second = store.reserve(dict(command, task_id="task_rr"), lambda *_: ([], 8))
    assert second["sender"] == "g1"


def test_live_managed_event_not_double_counted(store, command):
    row = store.reserve(command, lambda *_: ([], 1))
    row["data"]["barbara"] = {"id": "local"}
    store.save(row["operation"], "linked", row["data"], "test")
    second = store.reserve(dict(command, task_id="task_two"), lambda *_: ([{"id": "local"}], 2))
    assert second["task_id"] == "task_two"


def test_jobs_restart_lease_expiry_fencing_and_meeting_serialization(store, command):
    row = store.reserve(command, lambda *_: ([], 1))
    first = store.claim()
    assert store.claim() is None
    with store.connect() as c:
        c.execute("UPDATE bridge_jobs SET lease_until=now()-interval '1 second'")
    second = store.claim()
    assert first["lease_token"] != second["lease_token"]
    store.finish_job(first, 999)
    with store.connect() as c:
        assert c.execute("SELECT lease_token FROM bridge_jobs").fetchone()["lease_token"] == second["lease_token"]
    with store.meeting_lock(row["operation"]) as locked:
        assert locked
        with store.meeting_lock(row["operation"]) as other:
            assert not other
    store.finish_job(second, 0)
    assert store.claim() is not None
