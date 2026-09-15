"""Load named legacy seams without importing Streamlit or opening its secrets."""
import ast
from pathlib import Path
import types
import sys

import pytest


def function(name, globals, file="calendar_utils.py"):
    source=ast.parse(Path(file).read_text())
    node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),file,"exec"),globals)
    return globals[name]


class Rerun(Exception):
    pass


class FakeStreamlit:
    def __init__(self,**state):
        self.session_state=types.SimpleNamespace(**state)
    def rerun(self):
        raise Rerun()


def bridge_advance(tasks,index):
    st=FakeStreamlit(tasks=tasks,current_task_index=index,review_mode=True,template_title="Hi {first}",
                     template_description="Meet {first}",current_title="stale",current_description="stale")
    utils=types.SimpleNamespace(format_template=lambda template,task:template.replace("{first}",task["first"]))
    advance=function("advance_review_after_bridge",{"st":st,"calendar_utils":utils},"blind_invite.py")
    return st,advance


def test_bridge_review_advances_to_next_lead_templates_and_reruns():
    tasks=[{"id":"task_a","first":"Ann"},{"id":"task_b","first":"Bo"}]
    st,advance=bridge_advance(tasks,0)
    with pytest.raises(Rerun):
        advance("task_a","Bridge operation: reserved")
    assert [t["id"] for t in st.session_state.tasks]==["task_b"]
    assert st.session_state.current_task_index==0
    assert st.session_state.current_title=="Hi Bo" and st.session_state.current_description=="Meet Bo"
    assert st.session_state.bridge_notice=="Bridge operation: reserved"
    assert st.session_state.review_mode is True


def test_bridge_review_last_task_clamps_index_and_exits_review():
    tasks=[{"id":"task_a","first":"Ann"},{"id":"task_b","first":"Bo"}]
    st,advance=bridge_advance(tasks,1)
    with pytest.raises(Rerun):
        advance("task_b","handled")
    assert st.session_state.current_task_index==0 and st.session_state.current_title=="Hi Ann"
    st,advance=bridge_advance([{"id":"task_a","first":"Ann"}],0)
    with pytest.raises(Rerun):
        advance("task_a","handled")
    assert st.session_state.tasks==[] and st.session_state.review_mode is False


def test_bridge_send_branches_advance_review_instead_of_returning_stale_state():
    source=Path("blind_invite.py").read_text()
    status=source.index("operation = bridge_client.operation_status(task[\"id\"])")
    submit=source.index("result = bridge_client.submit(")
    assert "advance_review_after_bridge(" in source[status:source.index("return",status)]
    assert "advance_review_after_bridge(" in source[submit:source.index("return",submit)]


class HttpError(Exception):
    pass


class Calendar:
    def __init__(self,pages):
        self.pages,self.params=pages,[]
    def events(self): return self
    def list(self,**kwargs):
        self.params.append(kwargs)
        return self
    def execute(self):
        item=self.pages.pop(0)
        if isinstance(item,Exception): raise item
        return item


def test_legacy_duplicate_lookup_error_does_not_block_and_does_not_claim_safe():
    # Production behaviour: a Calendar API blip must not stop the operator
    # working. It also must not report "safe to send", which would read as a
    # confirmed all-clear when nothing was actually checked.
    service=Calendar([HttpError("403")])
    check=function("check_lead_invite_exists",{"get_calendar_service":lambda:service,"get_current_calendar_id":lambda:"main","HttpError":HttpError})
    exists,detail=check("lead@example.test")
    assert exists is False
    assert "safe to send" not in str(detail).lower()
    assert "error" in str(detail).lower()


def test_legacy_duplicate_lookup_all_pages_and_success_unchanged():
    service=Calendar([{"items":[],"nextPageToken":"second"},{"items":[{"id":"legacy","summary":"Legacy intro","attendees":[{"email":"lead@example.test"}]}]}])
    check=function("check_lead_invite_exists",{"get_calendar_service":lambda:service,"get_current_calendar_id":lambda:"main","HttpError":HttpError})
    exists,details=check("lead@example.test")
    assert exists and details[0]["id"]=="legacy"
    assert service.params[1]["pageToken"]=="second"


def test_legacy_capacity_lookup_error_returns_empty_like_production():
    # Matches production: an error yields no events. That is fail-open and can
    # over-fill a block if Google errors mid-run, but it is the behaviour the
    # desk has always had and changing it silently would be worse.
    service=Calendar([HttpError("403")])
    get=function("get_events_in_range",{"get_calendar_service":lambda:service,"get_current_calendar_id":lambda:"main","HttpError":HttpError})
    assert get("2035-09-09T14:00:00+00:00","2035-09-09T14:30:00+00:00")==[]


def test_legacy_failed_create_guard_precedes_close_completion():
    source=Path("blind_invite.py").read_text()
    create=source.index("created_event = calendar_utils.create_calendar_invite")
    guard=source.index('if not created_event or not created_event.get("id"):',create)
    complete=source.index("mark_task_complete_in_close(",create)
    assert create<guard<complete
    assert 'raise ValueError("Calendar creation was not confirmed; Close task was not completed.")' in source[guard:complete]


def test_barbara_only_feature_flag_off_and_april_unchanged(monkeypatch):
    fake=types.ModuleType("streamlit")
    fake.session_state={"selected_consultant":"barbara_pigg"}
    monkeypatch.setitem(sys.modules,"streamlit",fake)
    sys.modules.pop("bridge_client",None)
    import bridge_client
    monkeypatch.delenv("CALENDAR_BRIDGE_UI_ENABLED",raising=False)
    assert not bridge_client.enabled()
    monkeypatch.setenv("CALENDAR_BRIDGE_UI_ENABLED","true")
    assert bridge_client.enabled()
    fake.session_state["selected_consultant"]="april_lowrie"
    assert not bridge_client.enabled()
