from deeptutor.api.routers.auth import _learning_surface_for_path
from deeptutor.modules import catalog


def test_obsidian_router_has_independent_learning_registration_and_packaging():
    row = catalog.manifests()["knowledge"]
    route = next(
        (r for r in row["routes"] if r["reference"] == "deeptutor.api.routers.obsidian:router"),
        None,
    )
    assert route is not None
    assert route["options"]["prefix"] == "/api"
    assert route["auth"] == "learning"
    assert "deeptutor/services/obsidian_learning.py" in row["paths"]
    assert "deeptutor/api/routers/obsidian.py" in row["paths"]
    assert "/api/obsidian" in row["http_paths"]
    assert "/obsidian" in row["navigation"]


def test_obsidian_learning_endpoints_are_in_chat_surface():
    for path, method in [
        ("/api/obsidian/note", "GET"),
        ("/api/obsidian/material", "POST"),
        ("/api/obsidian/drafts/id/save", "POST"),
    ]:
        assert _learning_surface_for_path(path, method) == "chat"
