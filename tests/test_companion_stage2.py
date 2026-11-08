import pytest

from deeptutor.multi_user.context import get_current_user
from deeptutor.services.memory import get_memory_store
from deeptutor.services.memory.trace import TraceEvent


@pytest.mark.asyncio
async def test_study_trace_drives_mobile_greeting(tmp_path, monkeypatch):
    from deeptutor.services.companion.study_memory_bridge import build_mobile_greeting_context
    from deeptutor.services.companion.teen_personas import greeting
    from deeptutor.services.path_service import PathService

    monkeypatch.setattr(PathService, "_instance", PathService(workspace_root=tmp_path))
    event = TraceEvent.new(
        "chat",
        "study_completed",
        {
            "topic": "二次方程",
            "duration_seconds": 120,
            "reward": {"energy_points": 30, "item": {"name": "Math fragment"}},
        },
    )
    store = get_memory_store()
    await store.emit(event)
    await store.apply_ops_payload(
        "L2",
        "chat",
        [
            {
                "op": "add",
                "section": "Study",
                "text": "能解二次方程",
                "refs": [event.id],
            }
        ],
    )
    context = build_mobile_greeting_context(get_current_user().id)
    assert context["duration_seconds"] == 120
    assert context["facts"] == ["能解二次方程"]
    result = greeting("cyber_navigator", context)
    assert "二次方程" in result["text"]
    assert result["emotion_state"] == "proud"
    assert result["reward_bubble"]["item"]["name"] == "Math fragment"


@pytest.mark.asyncio
async def test_treehole_memory_is_auditable(tmp_path, monkeypatch):
    from deeptutor.services.companion.study_memory_bridge import remember_treehole
    from deeptutor.services.companion.teen_personas import parse_reply
    from deeptutor.services.memory.trace import iter_since
    from deeptutor.services.path_service import PathService

    monkeypatch.setattr(PathService, "_instance", PathService(workspace_root=tmp_path))
    reply = parse_reply('{"text":"我听到了。","emotion_state":"empathetic"}')
    assert reply["emotion_state"] == "empathetic"
    await remember_treehole("这周希望先整理复习计划", reply["emotion_state"])
    entry = list(get_memory_store().read_doc("L2", "partner").all_entries())[0]
    assert "复习计划" in entry.text
    assert entry.refs == [next(iter_since("partner")).id]
