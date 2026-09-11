from copy import deepcopy
from fastapi.testclient import TestClient
import pytest

from bridge.api import create_app
from bridge.domain import Blocked
from bridge.providers import ProviderError
from test_api_postgres import auth
from test_worker_postgres import linked,pair,later


def test_operator_time_conflict_resolution_requires_fresh_both_revisions(worker,command):
    meeting=linked(worker,command)
    o,b,oi,bi=pair(worker,meeting)
    o.update(oi,**later(o.events[oi],15))
    b.update(bi,**later(b.events[bi],16))
    worker.process(meeting["operation"])
    with TestClient(create_app(worker.settings,worker.store,worker.providers,worker.crm)) as client:
        path="/meetings/"+meeting["operation"]+"/resolve-time"
        body={"source":"barbara","organizer_revision":o.events[oi]["etag"],"barbara_revision":'"stale"'}
        assert client.post(path,json=body,headers=auth()).status_code==409
        body["barbara_revision"]=b.events[bi]["etag"]
        assert client.post(path,json=body,headers=auth()).status_code==200
        assert o.events[oi]["start"]==b.events[bi]["start"]


def test_unknown_hard_deletion_needs_two_step_authenticated_full_link_confirmation(worker,command):
    meeting=linked(worker,command)
    o,b,oi,bi=pair(worker,meeting)
    del b.events[bi]
    with pytest.raises(ProviderError):
        worker.process(meeting["operation"])
    with TestClient(create_app(worker.settings,worker.store,worker.providers,worker.crm)) as client:
        path="/meetings/"+meeting["operation"]
        assert client.post(path+"/deletion-review",json={"side":"barbara"}).status_code==401
        evidence=client.post(path+"/deletion-review",json={"side":"barbara"},headers=auth())
        assert evidence.status_code==200,evidence.text
        body={k:evidence.json()[k] for k in ("side","expected_version","confirmation_token")}
        body.update(actor="reviewed operator",reason="Verified actual deletion in provider audit, not a move")
        assert client.post(path+"/confirm-deletion",json=dict(body,confirmation_token="wrong"),headers=auth()).status_code==409
        assert client.post(path+"/confirm-deletion",json=body,headers=auth()).status_code==200
        assert client.post(path+"/confirm-deletion",json=body,headers=auth()).status_code==409
    worker.process(meeting["operation"])
    assert o.events[oi]["status"]=="cancelled"


def test_deletion_review_rejects_live_events_and_auth_failures(worker,command):
    meeting=linked(worker,command)
    o,b,oi,bi=pair(worker,meeting)
    with TestClient(create_app(worker.settings,worker.store,worker.providers,worker.crm)) as client:
        path="/meetings/"+meeting["operation"]+"/deletion-review"
        assert client.post(path,json={"side":"organizer"},headers=auth()).status_code==409
        o.auth_error=403
        result=client.post(path,json={"side":"organizer"},headers=auth())
        assert result.status_code==409
        assert "provider_http_403" in result.text
    assert "cancel" not in b.writes


def test_provider_412_records_explicit_conflict_not_retry_overwrite(worker,command,monkeypatch):
    meeting=linked(worker,command)
    o,b,oi,bi=pair(worker,meeting)
    b.update(bi,**later(b.events[bi],15))
    def raced(*_):
        o.update(oi,**later(o.events[oi],16))
        raise ProviderError(412)
    monkeypatch.setattr(o,"patch_time",raced)
    worker.tick()
    row=worker.store.get(meeting["operation"])
    assert row["state"]=="sync_conflict"
    assert row["data"]["conflict"]["kind"]=="provider_precondition_failed"


def test_rsvp_rebase_does_not_swallow_new_local_time(worker,command,monkeypatch):
    meeting=linked(worker,command)
    o,b,oi,bi=pair(worker,meeting)
    o.update(oi,attendees=[{"email":"lead@example.test","responseStatus":"accepted"}])
    project=b.project_rsvp
    def concurrent(original,live,email):
        b.update(bi,**later(b.events[bi],15))
        return project(original,b.get(bi),email)
    monkeypatch.setattr(b,"project_rsvp",concurrent)
    worker.process(meeting["operation"])
    assert o.events[oi]["start"]!=b.events[bi]["start"]
    worker.process(meeting["operation"])
    assert o.events[oi]["start"]==b.events[bi]["start"]


def test_disable_after_reservation_blocks_unattempted_sender(worker,command):
    meeting=worker.store.reserve(command,lambda *_:([],8))
    worker.store.disable(meeting["sender"],True,"operator retired")
    with pytest.raises(Blocked,match="reserved_sender_retired"):
        worker.process(meeting["operation"])
    assert not worker.providers.providers[meeting["sender"]].writes


EVIDENCE={"actor":"reviewed operator","reason":"Reviewed with Barbara; documented in the operations log"}


def test_local_guest_edit_conflict_has_acknowledge_exit(worker,command):
    meeting=linked(worker,command)
    o,b,oi,bi=pair(worker,meeting)
    o.update(oi,attendees=[{"email":"lead@example.test","responseStatus":"accepted"}])
    b.update(bi,attendees=b.events[bi]["attendees"]+[{"email":"colleague@example.test"}])
    worker.process(meeting["operation"])
    row=worker.store.get(meeting["operation"])
    assert row["state"]=="sync_conflict" and row["data"]["conflict"]["kind"]=="unsupported_local_guest_edit"
    with TestClient(create_app(worker.settings,worker.store,worker.providers,worker.crm)) as client:
        path="/meetings/"+meeting["operation"]+"/acknowledge-guests"
        assert client.post(path,json=EVIDENCE).status_code==401
        assert client.post(path,json={"actor":"x","reason":"short"},headers=auth()).status_code==422
        assert client.post(path,json=EVIDENCE,headers=auth()).status_code==200
        assert "no_local_guest_edit_conflict" in client.post(path,json=EVIDENCE,headers=auth()).text
    worker.process(meeting["operation"])
    row=worker.store.get(meeting["operation"])
    assert row["state"]=="complete" and "conflict" not in row["data"]
    assert b.events[bi]["attendees"][0]["responseStatus"]=="accepted"
    assert "rsvp" not in o.writes and o.events[oi]["attendees"]==[{"email":"lead@example.test","responseStatus":"accepted"}]
    with worker.store.connect() as c:
        assert c.execute("SELECT count(*) AS n FROM bridge_audit WHERE action='guest_edit_evidence'").fetchone()["n"]==1


@pytest.mark.parametrize("cancelled_side",["organizer","barbara"])
def test_cancellation_versus_reschedule_conflict_resolves_only_toward_cancellation(worker,command,cancelled_side):
    meeting=linked(worker,command)
    o,b,oi,bi=pair(worker,meeting)
    gone,going,survivor,si=(o,oi,b,bi) if cancelled_side=="organizer" else (b,bi,o,oi)
    gone.update(going,status="cancelled")
    survivor.update(si,**later(survivor.events[si],15))
    worker.process(meeting["operation"])
    assert worker.store.get(meeting["operation"])["state"]=="sync_conflict"
    with TestClient(create_app(worker.settings,worker.store,worker.providers,worker.crm)) as client:
        conflict=client.get("/meetings/"+meeting["operation"],headers=auth()).json()["conflict"]
        body={"organizer_revision":conflict["organizer"]["etag"],"barbara_revision":conflict["barbara"]["etag"]}
        path="/meetings/"+meeting["operation"]+"/resolve-time"
        revive=client.post(path,json=dict(body,source="barbara" if cancelled_side=="organizer" else "organizer"),headers=auth())
        assert revive.status_code==409 and "cancelled_side_cannot_be_revived" in revive.text
        assert "time" not in o.writes+b.writes
        resolved=client.post(path,json=dict(body,source=cancelled_side),headers=auth())
        assert resolved.status_code==200 and resolved.json()["status"]=="cancelled"
    row=worker.store.get(meeting["operation"])
    assert row["state"]=="cancelled" and "conflict" not in row["data"]
    assert o.events[oi]["status"]==b.events[bi]["status"]=="cancelled"
    assert "time" not in o.writes+b.writes


def test_confirmed_deletion_then_reschedule_conflict_does_not_loop(worker,command):
    meeting=linked(worker,command)
    o,b,oi,bi=pair(worker,meeting)
    o.update(oi,**later(o.events[oi],15))
    del b.events[bi]
    with pytest.raises(ProviderError):
        worker.process(meeting["operation"])
    with TestClient(create_app(worker.settings,worker.store,worker.providers,worker.crm)) as client:
        path="/meetings/"+meeting["operation"]
        evidence=client.post(path+"/deletion-review",json={"side":"barbara"},headers=auth()).json()
        body={k:evidence[k] for k in ("side","expected_version","confirmation_token")}|EVIDENCE
        assert client.post(path+"/confirm-deletion",json=body,headers=auth()).status_code==200
        worker.process(meeting["operation"])
        assert worker.store.get(meeting["operation"])["state"]=="sync_conflict"
        conflict=client.get(path,headers=auth()).json()["conflict"]
        resolve={"source":"barbara","organizer_revision":conflict["organizer"]["etag"],"barbara_revision":conflict["barbara"]["etag"]}
        assert client.post(path+"/resolve-time",json=resolve,headers=auth()).status_code==200
    assert worker.store.get(meeting["operation"])["state"]=="cancelled"
    assert o.events[oi]["status"]=="cancelled"


def test_void_releases_only_unattempted_reservations(worker,command):
    stuck=worker.store.reserve(command,lambda *_:([],1))
    worker.store.disable(stuck["sender"],True,"operator retired")
    with pytest.raises(Blocked):
        worker.process(stuck["operation"])
    with pytest.raises(Blocked,match="slot_at_capacity"):
        worker.store.reserve(dict(command,task_id="task_next"),lambda *_:([],1))
    with TestClient(create_app(worker.settings,worker.store,worker.providers,worker.crm)) as client:
        path="/meetings/"+stuck["operation"]+"/void"
        assert client.post(path,json=EVIDENCE).status_code==401
        assert client.post("/meetings/unmanaged/void",json=EVIDENCE,headers=auth()).status_code==404
        assert client.post(path,json=EVIDENCE,headers=auth()).status_code==200
        assert "already_cancelled" in client.post(path,json=EVIDENCE,headers=auth()).text
        sent=linked(worker,dict(command,task_id="task_sent",start="2035-09-10T14:00:00+00:00",end="2035-09-10T14:30:00+00:00"))
        refused=client.post("/meetings/"+sent["operation"]+"/void",json=EVIDENCE,headers=auth())
        assert refused.status_code==409 and "void_requires_unattempted_reservation" in refused.text
    assert worker.store.get(stuck["operation"])["state"]=="cancelled"
    assert worker.store.reserve(dict(command,task_id="task_next"),lambda *_:([],1))["state"]=="reserved"
    worker.process(stuck["operation"])
    assert not worker.providers.providers[stuck["sender"]].writes
    with worker.store.connect() as c:
        assert c.execute("SELECT count(*) AS n FROM bridge_audit WHERE action='void_evidence'").fetchone()["n"]==1
