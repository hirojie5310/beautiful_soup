from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_screen_shared_exposes_step_menu_member_selection() -> None:
    source = _read("web_wasm/screens/screen_shared.js")

    assert "export function stepMenuMemberSelection" in source
    assert "const nextIndex = ((safeBaseIndex + safeStep) % party.length + party.length) % party.length;" in source
    assert "store.patch({ menuMemberIndex: nextIndex });" in source


def test_magic_equip_status_job_screens_use_shared_member_stepper() -> None:
    targets = [
        "web_wasm/screens/magic_screen.js",
        "web_wasm/screens/equip_screen.js",
        "web_wasm/screens/status_screen.js",
        "web_wasm/screens/job_screen.js",
    ]

    for path in targets:
        source = _read(path)
        assert "stepMenuMemberSelection" in source, path
        assert "stepMenuMemberSelection(store," in source, path
        assert "const onLeft = () => {" in source, path
        assert "const onRight = () => {" in source, path


def test_subpage_navigation_buttons_prevent_default_before_handling() -> None:
    source = _read("web_wasm/screens/screen_shared.js")

    assert "const onLeftClick = (event) => {" in source
    assert "const onRightClick = (event) => {" in source
    assert "const onBackClick = (event) => {" in source
    assert source.count("event.preventDefault();") >= 3
    assert source.count("event.stopPropagation();") >= 3
