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


def test_menu_party_row_uses_portrait_offset_instead_of_text() -> None:
    menu_source = _read("web_wasm/screens/menu_screen.js")
    css_source = _read("web_wasm/index.html")

    assert 'card.classList.add(`row-${normalizeRow(member?.row)}`);' in menu_source
    assert '<div class="muted">row:' not in menu_source
    assert "grid-template-columns: 84px 1fr;" in css_source
    assert ".member-card.row-back .portrait" in css_source
    assert "justify-self: end;" in css_source


def test_menu_party_hp_row_renders_status_icons() -> None:
    menu_source = _read("web_wasm/screens/menu_screen.js")
    css_source = _read("web_wasm/index.html")

    assert 'class="menu-status-icons"' in menu_source
    assert "memberStatusIconKeys(member).forEach" in menu_source
    assert "resolveStatusIconCandidates(iconKey)" in menu_source
    assert ".menu-status-icon" in css_source
    assert "width: 16px;" in css_source
