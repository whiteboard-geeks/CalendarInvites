from dataclasses import replace
from fastapi.testclient import TestClient
import pytest

from bridge.api import create_app
from bridge.domain import Blocked
from conftest import FakeProviders, FakeCRM


@pytest.fixture
def client(settings, store, registry):
    app=create_app(settings,store,FakeProviders(registry),FakeCRM())
    with TestClient(app) as client:
        yield client


def auth():
    return {"Authorization":"Bearer " + "a"*40}


def test_auth_startup_health_and_readiness(client,store):
    assert client.get("/healthz").status_code==200
    assert client.get("/inventory").status_code==401
    assert client.get("/meetings",headers={"Authorization":"Bearer wrong"}).status_code==401
    assert client.get("/readyz").status_code==503
    store.heartbeat()
    assert client.get("/readyz").status_code==200
    result=client.get("/inventory",headers=auth())
    assert result.status_code==200
    assert "credential_secret" not in result.text
    assert result.json()["groups"]["google"]=={"eligible":2,"total":2}


def test_submit_idempotent_group_changes_apply_to_new_only(client,command,store):
    first=client.post("/invites",json=command,headers=auth())
    assert first.status_code==200,first.text
    retry=client.post("/invites",json=dict(command,groups=["microsoft"]),headers=auth())
    assert retry.json()==first.json()
    assert store.get(first.json()["operation"])["group_name"]=="google"


def test_no_unauthenticated_action_and_invalid_calendar_injection(client,command):
    assert client.post("/invites",json=command).status_code==401
    result=client.post("/invites",json=dict(command,calendar_id="attacker"),headers=auth())
    assert result.status_code==422
    assert "attacker" not in result.text
    assert client.post("/meetings/unmanaged/reconcile",headers=auth()).status_code==404
    assert client.post("/webhooks/google",json={}).status_code==404


@pytest.mark.parametrize("changes,reason", [({"new_sends":False},"new_sends_disabled"),
    ({"dry_run":True},"dry_run"),({"import_cas_verified":False},"outreach_release_blocked")])
def test_feature_flags_fail_closed(settings,store,registry,command,changes,reason):
    with TestClient(create_app(replace(settings,**changes),store,FakeProviders(registry),FakeCRM())) as client:
        response=client.post("/invites",json=command,headers=auth())
        assert response.status_code==409
        assert reason in response.text


def test_startup_rejects_short_auth_token(settings,store,registry):
    with pytest.raises(Blocked,match="operator_token_too_short"):
        with TestClient(create_app(replace(settings,operator_token="short"),store,FakeProviders(registry))):
            pass


def test_audited_disable_excludes_new_sends(client,store):
    response=client.post("/senders/g1/disable",json={"disabled":True,"reason":"retire reviewed sender"},headers=auth())
    assert response.status_code==200
    row=next(a for a in client.get("/inventory",headers=auth()).json()["accounts"] if a["id"]=="g1")
    assert "disabled_for_new_sends" in row["exclusions"]
    with store.connect() as c:
        assert c.execute("SELECT count(*) AS n FROM bridge_audit WHERE action='sender_disable'").fetchone()["n"]==1


@pytest.mark.parametrize("value,status", [(1, 200), (8, 200), (40, 200), (100, 200), (0, 422), (101, 422)])
def test_operator_chooses_leads_per_block_within_model_bounds(client, command, value, status):
    # No server-side reviewed ceiling: the operator's value governs slot capacity and is
    # bounded only by Invite.leads_per_block (1..100).
    response = client.post("/invites", json=dict(command, task_id="task_cap%d" % value,
                                                 leads_per_block=value), headers=auth())
    assert response.status_code == status, response.text
    assert "capacity_exceeds_reviewed_limit" not in response.text
