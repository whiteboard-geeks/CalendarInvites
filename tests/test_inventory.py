from copy import deepcopy
from datetime import datetime,timezone
import pytest

from bridge.domain import Blocked,exclusion_reasons
from bridge.inventory import Instantly
from test_providers import Scripted


def test_paginated_read_only_inventory_including_empty_terminal_page(monkeypatch):
    monkeypatch.setattr("bridge.inventory.time.sleep",lambda *_:None)
    http=Scripted([{"items":[{"email":"one@example.test"}],"next_starting_after":"opaque&one"},
                   {"items":[],"next_starting_after":None}])
    accounts=Instantly(http,{}).accounts()
    assert len(accounts)==1
    assert all(c[0]=="GET" for c in http.calls)
    assert http.calls[1][2]["params"]["starting_after"]=="opaque&one"


@pytest.mark.parametrize("provider,expected",[(1,None),(2,"google"),(3,"microsoft"),(4,None)])
def test_official_provider_mapping_not_domain_guess(monkeypatch,registry,provider,expected):
    monkeypatch.setattr("bridge.inventory.time.sleep",lambda *_:None)
    account=registry["senders"][1]
    today=datetime.now(timezone.utc).date().isoformat()
    http=Scripted([{"status":1,"provider_code":provider,"warmup_status":1,"setup_pending":False},
        {"items":[{"campaign_id":"campaign-reviewed","status":4}]},
        {"status":4,"email_list":[account["email"]]},
        [{"date":today,"email_account":account["email"],"sent":3}]] )
    health=Instantly(http,{}).observe(account)
    assert health["provider"]==expected
    assert health["active_campaigns"]==["campaign-reviewed"]
    assert health["usage"]==3
    assert all(c[0]=="GET" for c in http.calls)


def test_campaign_pause_not_account_pause_and_policy_explicit(monkeypatch,registry):
    monkeypatch.setattr("bridge.inventory.time.sleep",lambda *_:None)
    account=deepcopy(registry["senders"][1])
    responses=[{"status":1,"provider_code":2,"setup_pending":False},
        {"items":[{"campaign_id":"campaign-reviewed","status":2}]},
        {"status":2,"email_list":[account["email"]]},Blocked("metrics_unavailable")]
    paused_campaign=Instantly(Scripted(responses),{}).observe(account)
    assert paused_campaign["connected"]
    assert not paused_campaign["active_campaigns"]
    account["health"].update(paused_campaign)
    assert not exclusion_reasons(account,__import__('time').time())
    # A paused ACCOUNT is paused for cold email. It stays usable for calendar
    # invites: still warmed, authenticated and healthy. Only genuine error or
    # maintenance states exclude.
    paused_account=Instantly(Scripted([{"status":2,"provider_code":2,"setup_pending":False},
        {"items":[]},Blocked("metrics_unavailable")]),{}).observe(account)
    account["health"].update(paused_account)
    assert not paused_account["connected"]
    assert "instantly_unusable" not in exclusion_reasons(account,__import__('time').time())
    broken_account=Instantly(Scripted([{"status":-1,"provider_code":2,"setup_pending":False},
        {"items":[]},Blocked("metrics_unavailable")]),{}).observe(account)
    account["health"].update(broken_account)
    assert "instantly_unusable" in exclusion_reasons(account,__import__('time').time())


def test_cursor_loop_fails_closed(monkeypatch):
    monkeypatch.setattr("bridge.inventory.time.sleep",lambda *_:None)
    http=Scripted([{"items":[],"next_starting_after":"same"}]*2)
    with pytest.raises(Blocked,match="pagination_loop"):
        Instantly(http,{}).accounts()
