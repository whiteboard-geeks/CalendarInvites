from copy import deepcopy
import pytest

from bridge.domain import Blocked, private_body
from bridge.providers import Google, Graph, ProviderError, graph_event, graph_time, GRAPH_OPERATION_PROPERTY
from test_domain import event


class Scripted:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def call(self, method, path, **kwargs):
        self.calls.append((method,path,deepcopy(kwargs)))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)


def google(transport, enabled=True):
    return Google({"calendar_id":"main@example.test"},transport,enabled)


def local():
    return dict(private_body(event(),"barbara@example.test"),id="copy",etag='"real-old"',privateCopy=True)


def test_google_deterministic_id_reconciles_timeout_same_sender():
    http = Scripted([ProviderError(404),Blocked("timeout"),event()])
    api = google(http)
    with pytest.raises(Blocked):
        api.create("abc123",event())
    assert api.create("abc123",event())["id"] == "event"
    assert [c[0] for c in http.calls] == ["GET","POST","GET"]
    assert http.calls[1][2]["body"]["id"] == "abc123"


def test_import_412_rebases_rsvp_onto_latest_local_fields_with_real_etag():
    original = event()
    original["attendees"][0]["responseStatus"] = "accepted"
    old = local()
    fresh = dict(old, etag='"real-new"', summary="✅ New local title", location="New location",
                 description="Local notes", reminders={"useDefault":True},colorId="7",
                 extendedProperties={"private":{"automation":"keep"}})
    projected = dict(fresh,attendees=private_body(original,"barbara@example.test",fresh)["attendees"])
    http = Scripted([ProviderError(412),fresh,projected,projected])
    result = google(http).project_rsvp(original,old,"barbara@example.test")
    assert result["id"] == old["id"]
    first,second = http.calls[0],http.calls[2]
    assert first[2]["headers"]["If-Match"] == '"real-old"'
    assert second[2]["headers"]["If-Match"] == '"real-new"'
    for key in ("summary","location","description","reminders","colorId","extendedProperties"):
        assert second[2]["body"][key] == fresh[key]


def test_import_rebase_bounded_and_disabled_capability_never_writes():
    old=local()
    http=Scripted([ProviderError(412),old,ProviderError(412),old,ProviderError(412)])
    with pytest.raises(Blocked,match="rsvp_degraded_concurrent_local_edits"):
        google(http).project_rsvp(event(),old,"barbara@example.test")
    assert len(http.calls)==5
    no_calls=Scripted([])
    with pytest.raises(Blocked,match="unproven"):
        google(no_calls,False).project_rsvp(event(),old,"barbara@example.test")
    assert not no_calls.calls


def test_private_copy_assertion_rejects_organizer_owned_import():
    with pytest.raises(Blocked,match="private_copy_invariant"):
        Google.assert_copy(dict(local(),privateCopy=False),event(),"barbara@example.test")


def test_google_time_patch_only_time_and_exact_precondition():
    http=Scripted([local()])
    google(http).patch_time(local(),event(11))
    method,path,kwargs=http.calls[0]
    assert method=="PATCH"
    assert set(kwargs["body"])=={"start","end"}
    assert kwargs["headers"]["If-Match"]=='"real-old"'
    assert kwargs["params"]["sendUpdates"]=="none"


def graph_raw(response="notResponded"):
    return {"id":"immutable", "@odata.etag":'W/"real-tag"', "iCalUId":"uid", "subject":"Intro",
        "start":{"dateTime":"2035-09-09T14:00:00","timeZone":"UTC"},
        "end":{"dateTime":"2035-09-09T14:30:00","timeZone":"UTC"},
        "organizer":{"emailAddress":{"address":"sender@example.test"}},
        "attendees":[{"emailAddress":{"address":"lead@example.test"},"status":{"response":response}}]}


@pytest.mark.parametrize("response,expected", [("notResponded","needsAction"),("accepted","accepted"),
    ("tentativelyAccepted","tentative"),("declined","declined")])
def test_graph_rsvp_mapping(response,expected):
    assert graph_event(graph_raw(response))["attendees"][0]["responseStatus"]==expected


def test_graph_stable_transaction_and_immutable_id_header():
    recovered = dict(graph_raw(), singleValueExtendedProperties=[{"id":GRAPH_OPERATION_PROPERTY,"value":"a"*64}])
    http=Scripted([{"value":[]},graph_raw(),{"value":[recovered]}])
    api=Graph({"subject":"sender@example.test","email":"sender@example.test","calendar_id":"calendar"},http)
    first=api.create("a"*64,event())
    retry=api.create("a"*64,event())
    assert first["id"]==retry["id"]
    assert http.calls[1][2]["body"]["transactionId"]=="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert 'IdType="ImmutableId"' in http.calls[1][2]["headers"]["Prefer"]
    assert len([c for c in http.calls if c[0]=="POST"])==1


def test_graph_uses_real_etag_and_does_not_treat_500_as_conflict():
    http=Scripted([ProviderError(500)])
    api=Graph({"subject":"sender@example.test","calendar_id":"calendar"},http)
    with pytest.raises(ProviderError) as error:
        api.patch_time(graph_event(graph_raw()),event(11))
    assert error.value.status==500
    assert http.calls[0][2]["headers"]["If-Match"]=='W/"real-tag"'


def test_graph_timezone_roundtrip_keeps_zone_and_dst_instant():
    raw = dict(graph_raw(), originalStartTimeZone="Eastern Standard Time", originalEndTimeZone="Eastern Standard Time")
    converted = graph_event(raw)
    assert converted["start"]["timeZone"] == "America/New_York"
    assert converted["start"]["dateTime"] == "2035-09-09T14:00:00+00:00"
    assert graph_time(converted["start"]) == {"dateTime": "2035-09-09T10:00:00", "timeZone": "America/New_York"}


def test_google_uid_copy_recovery_will_not_recreate_tombstone():
    http = Scripted([{"items": [{"id": "copy", "status": "cancelled"}]}])
    with pytest.raises(Blocked, match="copy_cancelled_during_creation"):
        google(http).ensure_copy(event(), "barbara@example.test")
    assert all(c[0] == "GET" for c in http.calls)


def test_graph_recovery_wrong_marker_fails_closed():
    http = Scripted([{"value": [graph_raw()]}])
    api = Graph({"subject": "sender@example.test", "email": "sender@example.test", "calendar_id": "calendar"}, http)
    with pytest.raises(Blocked, match="graph_recovery_identity_mismatch"):
        api.create("a" * 64, event())
    assert all(c[0] == "GET" for c in http.calls)


def test_google_authorized_user_map_selects_mailbox(monkeypatch):
    import json
    from bridge.providers import google_token
    payload = {"type": "authorized_user_map", "client_id": "id", "client_secret": "sec",
               "accounts": {"a@x.test": {"refresh_token": "ra"}, "b@x.test": {"refresh_token": "rb"}}}
    monkeypatch.setattr("bridge.providers.secret", lambda name: json.dumps(payload))
    seen = []
    class Cred:
        valid, token = True, "tok"
    def fake_from_info(config, scopes):
        seen.append(config["refresh_token"])
        return Cred()
    monkeypatch.setattr("bridge.providers.oauth_credentials.Credentials.from_authorized_user_info", fake_from_info)
    assert google_token({"email": "B@x.test", "credential_secret": "GOOGLE_OUTREACH_CREDENTIAL"})() == "tok"
    assert seen == ["rb"]
    with pytest.raises(Blocked, match="provider_auth_unavailable"):
        google_token({"email": "missing@x.test", "credential_secret": "GOOGLE_OUTREACH_CREDENTIAL"})
