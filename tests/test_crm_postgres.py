import pytest
from bridge.crm import Close
from bridge.domain import Blocked


class ScriptedClose(Close):
    def __init__(self, settings, responses):
        self.settings,self.responses,self.calls=settings,list(responses),[]

    def call(self,method,path,body=None,params=None):
        self.calls.append((method,path,body,params))
        result=self.responses.pop(0)
        if isinstance(result,Exception):
            raise result
        return result


def meeting(store,command):
    row=store.reserve(command,lambda *_:([],8))
    row["data"].update(linked=True,organizer={"id":"organizer"},barbara={"id":"copy"})
    store.save(row["operation"],"linked",row["data"],"test_linked")
    return store.get(row["operation"])


def test_activity_timeout_never_blind_reposts_or_completes_task(settings,store,command):
    row=meeting(store,command)
    crm=ScriptedClose(settings,[Blocked("timeout")])
    with pytest.raises(Blocked):
        crm.advance(row,store)
    restarted=ScriptedClose(settings,[])
    with pytest.raises(Blocked,match="crm_uncertain"):
        restarted.advance(store.get(row["operation"]),store)
    assert not restarted.calls
    assert store.get(row["operation"])["state"]=="crm_uncertain"


def test_task_retry_does_not_recreate_activity(settings,store,command):
    row=meeting(store,command)
    crm=ScriptedClose(settings,[{"id":"acti_test"},Blocked("timeout"),{"is_complete":True}])
    with pytest.raises(Blocked):
        crm.advance(row,store)
    crm.advance(store.get(row["operation"]),store)
    assert [c[0] for c in crm.calls]==["POST","PUT","PUT"]
    assert store.get(row["operation"])["state"]=="complete"


def test_activity_from_email_reads_envelope_then_sender_header():
    from bridge.crm import Close
    assert Close.activity_from_email({"envelope":{"from":[{"email":"A@X.test"}]}})=="a@x.test"
    assert Close.activity_from_email({"sender":"Barbara <bpigg@wbgcontact.com>"})=="bpigg@wbgcontact.com"


def test_recent_from_addresses_newest_outgoing_sent(settings):
    crm=ScriptedClose(settings,[{"data":[
        {"direction":"outgoing","status":"draft","sender":"Skip <skip@x.test>"},
        {"direction":"incoming","status":"inbox","envelope":{"from":[{"email":"lead@x.test"}]}},
        {"direction":"outgoing","status":"sent","envelope":{"from":[{"email":"First@X.test"}]}},
        {"direction":"outgoing","date_sent":"2026-09-01T00:00:00Z","sender":"Second <second@x.test>"},
    ]}])
    assert crm.recent_from_addresses("lead_test")==["first@x.test","second@x.test"]


def test_operator_reconciliation_validates_existing_activity(settings,store,command):
    row=meeting(store,command)
    row["data"]["sent_date"]="2035-09-09"
    crm=ScriptedClose(settings,[])
    expected=crm.activity_body(row)
    crm.responses=[dict(expected,id="acti_test")]
    assert crm.validate_activity(row,"acti_test")=="acti_test"
    crm.responses=[dict(expected,id="acti_test",lead_id="lead_wrong")]
    with pytest.raises(Blocked,match="does_not_match"):
        crm.validate_activity(row,"acti_test")
