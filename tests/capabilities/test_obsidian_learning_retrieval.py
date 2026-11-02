"""Live-vault retrieval and graph behavior, using isolated fixture notes only."""

from pathlib import Path

import pytest

from deeptutor.capabilities.obsidian import vault as V


def note(root: Path, path: str, text: str = "body") -> Path:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_root_prefix_fallback_preserves_explicit_destination(tmp_path):
    root = tmp_path / "TA"
    original = note(root, "渲染/阴影.md")
    assert V.resolve_note(root, "TA/渲染/阴影#原理|显示") == original
    explicit = note(root, "TA/渲染/阴影.md", "different")
    assert V.resolve_note(root, "TA/渲染/阴影") == explicit


def test_aliases_resolve_exactly_and_report_ambiguity(tmp_path):
    target = note(tmp_path, "render/Shadow.md", "---\naliases: [阴影, Shadow Mapping]\n---\nbody")
    assert V.resolve_note(tmp_path, "阴影") == target
    assert V.resolve_note(tmp_path, "shadow mapping") == target
    assert V.resolve_note(tmp_path, "Shadow Map") is None
    note(tmp_path, "other/Other.md", "---\naliases: [阴影]\n---\nbody")
    with pytest.raises(V.VaultError, match="(?i)ambiguous") as error:
        V.read_note(tmp_path, "阴影")
    assert "render/Shadow.md" in str(error.value) and "other/Other.md" in str(error.value)


def test_duplicate_basenames_require_explicit_path(tmp_path):
    for folder in ("a", "b"):
        note(tmp_path, f"{folder}/Shared.md")
    with pytest.raises(V.VaultError, match="(?i)ambiguous"):
        V.read_note(tmp_path, "Shared")
    assert V.read_note(tmp_path, "b/Shared.md")["path"] == "b/Shared.md"


def test_wrapped_alias_and_heading_reference(tmp_path):
    target = note(tmp_path, "Target.md", '---\naliases: ["[[目标]]"]\n---\n# 原理\nbody')
    assert V.resolve_note(tmp_path, " [[目标#原理|显示]] ") == target


def test_prefix_fallback_cannot_expose_internal_notes(tmp_path):
    root = tmp_path / "TA"
    note(root, ".obsidian/Secret.md")
    with pytest.raises(V.VaultError):
        V.read_note(root, "TA/.obsidian/Secret#Heading")


def test_windows_junctions_cannot_escape_scans_or_direct_operations(tmp_path, monkeypatch):
    winapi = pytest.importorskip("_winapi")
    root = tmp_path / "vault"
    root.mkdir()
    outside = note(tmp_path, "outside/Secret.md", "secret #private")
    junction = root / "escape"
    winapi.CreateJunction(str(outside.parent), str(junction))
    # Python 3.11 has no Path.is_junction; reparse-point checks must still work.
    monkeypatch.delattr(Path, "is_junction", raising=False)
    assert V.list_notes(root) == []
    assert V.search_notes(root, "secret") == []
    assert V.collect_tags(root) == []
    for operation in (
        lambda: V.list_notes(root, "escape"),
        lambda: V.read_note(root, "escape/Secret.md"),
        lambda: V.create_note(root, "escape/New.md", "new"),
        lambda: V.append_note(root, "escape/Secret.md", "more"),
        lambda: V.set_property(root, "escape/Secret.md", "x", 1),
    ):
        with pytest.raises(V.VaultError):
            operation()
    assert outside.read_text(encoding="utf-8") == "secret #private"


@pytest.mark.parametrize("query", ["shadow mapping", "阴影 映射", "shadow 阴影"])
def test_multiterm_search_weights_metadata_over_body_and_is_stable(tmp_path, query):
    note(tmp_path, "a-body.md", "shadow mapping 阴影 映射 " * 100)
    note(tmp_path, "b-alias.md", "---\naliases: [shadow mapping, 阴影 映射]\n---\nbody")
    note(tmp_path, "c-tag.md", "---\ntags: [shadow, mapping, 阴影, 映射]\n---\nbody")
    note(tmp_path, "d-other.md", "unrelated")
    paths = [hit["path"] for hit in V.search_notes(tmp_path, query)]
    assert set(paths) == {"a-body.md", "b-alias.md", "c-tag.md"}
    assert paths.index("a-body.md") > paths.index("b-alias.md")
    assert paths.index("a-body.md") > paths.index("c-tag.md")
    assert V.search_notes(tmp_path, query, limit=1) == V.search_notes(tmp_path, query)[:1]
    assert V.search_notes(tmp_path, query) == V.search_notes(tmp_path, query)


def test_related_frontmatter_participates_in_graph(tmp_path):
    root = tmp_path / "TA"
    note(root, "Target.md", "---\naliases: [目标]\n---\nbody")
    note(root, "Source.md", '---\nrelated: ["[[TA/Target#Heading|label]]", 目标]\n---\n[[Other]]')
    assert V.outgoing_links(root, "Source") == ["Other", "TA/Target", "目标"]
    assert [row["path"] for row in V.backlinks(root, "Target")] == ["Source.md"]


@pytest.mark.parametrize("internal", [".obsidian", ".trash", ".git"])
def test_internal_paths_are_blocked_for_reads_lists_and_writes(tmp_path, internal):
    path = note(tmp_path, f"{internal}/Secret.md", "secret #hidden")
    assert V.list_notes(tmp_path) == []
    assert V.search_notes(tmp_path, "secret") == []
    assert V.collect_tags(tmp_path) == []
    for operation in (
        lambda: V.read_note(tmp_path, f"{internal}/Secret.md"),
        lambda: V.list_notes(tmp_path, internal),
        lambda: V.create_note(tmp_path, f"{internal}/New.md", "new"),
        lambda: V.append_note(tmp_path, f"{internal}/Secret.md", "more"),
        lambda: V.set_property(tmp_path, f"{internal}/Secret.md", "x", 1),
    ):
        with pytest.raises(V.VaultError):
            operation()
    assert path.read_text(encoding="utf-8") == "secret #hidden"


def test_symlinks_cannot_expose_external_or_internal_notes(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    outside = note(tmp_path, "outside/Secret.md", "secret #private")
    internal = note(root, ".obsidian/Hidden.md", "secret #private")
    try:
        (root / "Secret.md").symlink_to(outside)
        (root / "Hidden.md").symlink_to(internal)
        (root / "escape").symlink_to(outside.parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")
    assert V.list_notes(root) == []
    assert V.search_notes(root, "secret") == []
    assert V.collect_tags(root) == []
    for ref in ("Secret.md", "Hidden.md", "escape/Secret.md"):
        for operation in (
            lambda ref=ref: V.read_note(root, ref),
            lambda ref=ref: V.append_note(root, ref, "more"),
            lambda ref=ref: V.set_property(root, ref, "x", 1),
        ):
            with pytest.raises(V.VaultError):
                operation()
    with pytest.raises(V.VaultError):
        V.create_note(root, "escape/New.md", "new")
    assert outside.read_text(encoding="utf-8") == "secret #private"


@pytest.mark.parametrize("path", ["../escape", "..\\escape", "/outside", "C:\\outside"])
def test_unsafe_paths_rejected(tmp_path, path):
    with pytest.raises(V.VaultError):
        V.create_note(tmp_path, path, "body")


def test_limits_are_applied_after_ranking(tmp_path):
    note(tmp_path, "A.md", "target")
    note(tmp_path, "Target.md", "body")
    assert V.search_notes(tmp_path, "target", limit=1)[0]["path"] == "Target.md"
    assert V.search_notes(tmp_path, "target", limit=0) == []
    assert V.list_notes(tmp_path, limit=0) == []
    assert len(V.search_notes(tmp_path, "target", limit=None)) == 2
    assert len(V.list_notes(tmp_path, limit=None)) == 2
    assert V.search_notes(tmp_path, "  target  ") == V.search_notes(tmp_path, "target")


def test_backlinks_read_each_note_a_linear_number_of_times(tmp_path, monkeypatch):
    count = 100
    for index in range(count):
        note(tmp_path, f"Note{index:03}.md", f"[[Note{(index + 1) % count:03}]]")
    reads = 0
    original = V._read_text

    def counted_read(path):
        nonlocal reads
        reads += 1
        return original(path)

    monkeypatch.setattr(V, "_read_text", counted_read)
    assert [row["path"] for row in V.backlinks(tmp_path, "Note000")] == ["Note099.md"]
    assert reads <= count * 3


def test_unrelated_unreadable_note_does_not_break_resolution_or_backlinks(tmp_path, monkeypatch):
    good = note(tmp_path, "Good.md", "---\naliases: [Readable]\n---\nbody")
    note(tmp_path, "Broken.md")
    note(tmp_path, "Source.md", "[[Readable]]")
    original = V._read_text

    def unreadable(path):
        if path.name == "Broken.md":
            raise PermissionError("locked by another editor")
        return original(path)

    monkeypatch.setattr(V, "_read_text", unreadable)
    assert V.resolve_note(tmp_path, "Good") == good
    assert V.resolve_note(tmp_path, "Readable") == good
    assert [row["path"] for row in V.backlinks(tmp_path, "Good")] == ["Source.md"]
