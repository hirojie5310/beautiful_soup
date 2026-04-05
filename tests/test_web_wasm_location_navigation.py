from __future__ import annotations

from pathlib import Path


def test_location_index_links_to_split_shop_and_inn_pages() -> None:
    source = Path("web_wasm/index.html").read_text(encoding="utf-8")

    assert 'id="shopBtn"' in source
    assert 'id="innBtn"' in source
    assert "./location.js" in source
    assert 'id="shopMapSelect"' not in source
    assert 'id="stayInnBtn"' not in source


def test_shop_and_inn_pages_exist_with_dedicated_scripts() -> None:
    shop_html = Path("web_wasm/shop.html").read_text(encoding="utf-8")
    inn_html = Path("web_wasm/inn.html").read_text(encoding="utf-8")

    assert "./shop.js" in shop_html
    assert 'id="buyShopBtn"' in shop_html
    assert "./inn.js" in inn_html
    assert 'id="stayInnBtn"' in inn_html
