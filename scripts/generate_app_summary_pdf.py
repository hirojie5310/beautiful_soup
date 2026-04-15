from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "output" / "pdf"
OUTPUT_PATH = OUTPUT_DIR / "beautiful_soup_app_summary_ja.pdf"
JAPANESE_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
)


def register_fonts() -> tuple[str, str]:
    regular_name = "Helvetica"
    bold_name = "Helvetica-Bold"

    for candidate in JAPANESE_FONT_CANDIDATES:
        if not candidate.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("AppSummaryJP", str(candidate)))
            regular_name = "AppSummaryJP"
            bold_name = "AppSummaryJP"
            break
        except Exception:
            continue

    return regular_name, bold_name


def make_styles(font_name: str, bold_font_name: str) -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=styles["Heading1"],
            fontName=bold_font_name,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=8.6,
            leading=11,
            textColor=colors.HexColor("#4B5563"),
            spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=styles["Heading2"],
            fontName=bold_font_name,
            fontSize=11,
            leading=14,
            textColor=colors.white,
            backColor=colors.HexColor("#334155"),
            borderPadding=(4, 6, 4, 6),
            spaceBefore=4,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#111827"),
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=7.2,
            leading=9,
            textColor=colors.HexColor("#4B5563"),
        ),
    }


def draw_paragraph(
    canvas,
    text: str,
    style: ParagraphStyle,
    x: float,
    y_top: float,
    width: float,
) -> float:
    paragraph = Paragraph(text, style)
    _, height = paragraph.wrap(width, 1000)
    paragraph.drawOn(canvas, x, y_top - height)
    return y_top - height


def build_sections() -> dict[str, list[str] | str]:
    return {
        "what_it_is": (
            "FFIII風のターン制RPGを Web/Wasm 中心に実装したアプリです。"
            " `web_wasm` 配下ではタイトル、ロケーション、メニュー、戦闘、"
            "装備、魔法、ステータス、ジョブ画面が単一ページアプリとして構成されています。"
        ),
        "who_its_for": (
            "<b>明示的な一次ペルソナ:</b> Not found in repo.<br/>"
            "<b>Repo evidence suggests:</b> FFIIIライクなRPGをブラウザで試遊・検証したい"
            "開発者 / テスター / 制作者向け。"
        ),
        "features": [
            "タイトル画面でニューゲーム、コンテニュー、ロードを提供。",
            "ロケーション選択から battle / shop / inn / menu へ遷移。",
            "戦闘ラウンドをブラウザ内 Pyodide 上の Python エンジンで実行。",
            "item / equip / magic / status / job の各サブ画面を提供。",
            "AUTO SAVE と Slot 1-3 の手動保存を IndexedDB に保持。",
            "save envelope と menu_state を localStorage / IndexedDB へ同期。",
            "JSON Schema によるセーブ検証と旧 save の schema 移行を実装。",
        ],
        "architecture": [
            "<b>UI:</b> `web_wasm/index.html` を起点に `app.js` と `router.js` が SPA を起動し、`screens/*` を遅延読み込み。",
            "<b>状態管理:</b> `store/app_store.js` が route、location、menu_state、save envelope を保持。",
            "<b>保存:</b> `shared_storage.js` が localStorage と IndexedDB の save slot を扱う。",
            "<b>実行基盤:</b> `pyodide_runtime.js` が Pyodide、`typing-extensions`、`jsonschema`、`bootstrap_runtime.py` をロード。",
            "<b>Python bundle:</b> `scripts/build_wasm_bundle.py` が `combat` / `assets/data` / `schemas` / `system` / `utils` を `python_bundle.zip` に固める。",
            "<b>データフロー:</b> 画面操作 → store 更新 → Pyodide 上の `combat.wasm_api.WasmBattleEngine` / data loader 実行 → DTO / snapshot を UI に反映 → セーブ保存。",
            "<b>補助サーバ:</b> `wasm_app.py` は静的配信、`adapters/flask_app.py` は Flask / Gunicorn 起点として存在。",
        ],
        "how_to_run": [
            "1. `pip install -r requirements.txt`",
            "2. `python scripts/build_wasm_bundle.py`",
            "3. `python wasm_app.py`",
            "4. ブラウザで `http://127.0.0.1:8000/web_wasm/` を開く",
        ],
        "evidence": (
            "Evidence used: `README.md`, `web_wasm/ARCHITECTURE.md`, `web_wasm/router.js`, "
            "`web_wasm/store/app_store.js`, `web_wasm/shared_storage.js`, "
            "`web_wasm/pyodide_runtime.js`, `web_wasm/bootstrap_runtime.py`, "
            "`scripts/build_wasm_bundle.py`, `wasm_app.py`, `adapters/flask_app.py`."
        ),
    }


def build_pdf(output_path: Path) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    font_name, bold_font_name = register_fonts()
    styles = make_styles(font_name, bold_font_name)
    sections = build_sections()
    width, height = A4
    margin = 12 * mm
    gap = 8 * mm
    col_width = (width - (2 * margin) - gap) / 2
    left_x = margin
    right_x = margin + col_width + gap
    y = height - margin

    canvas = pdfcanvas.Canvas(str(output_path), pagesize=A4)

    y = draw_paragraph(
        canvas,
        "beautiful_soup アプリ概要",
        styles["title"],
        left_x,
        y,
        width - (2 * margin),
    ) - 2
    y = draw_paragraph(
        canvas,
        "Repo evidence のみを根拠に要約。情報が不足する項目は \"Not found in repo.\" と明示。",
        styles["subtitle"],
        left_x,
        y,
        width - (2 * margin),
    ) - 3

    left_y = y
    right_y = y

    left_y = draw_paragraph(canvas, "What It Is", styles["section"], left_x, left_y, col_width) - 3
    left_y = draw_paragraph(canvas, sections["what_it_is"], styles["body"], left_x, left_y, col_width) - 3
    left_y = draw_paragraph(canvas, "Who It's For", styles["section"], left_x, left_y, col_width) - 3
    left_y = draw_paragraph(canvas, sections["who_its_for"], styles["body"], left_x, left_y, col_width) - 3
    left_y = draw_paragraph(canvas, "What It Does", styles["section"], left_x, left_y, col_width) - 3
    for feature in sections["features"]:
        left_y = draw_paragraph(
            canvas,
            f"• {feature}",
            styles["body"],
            left_x,
            left_y,
            col_width,
        ) - 1

    right_y = draw_paragraph(canvas, "How It Works", styles["section"], right_x, right_y, col_width) - 3
    for item in sections["architecture"]:
        right_y = draw_paragraph(
            canvas,
            f"• {item}",
            styles["body"],
            right_x,
            right_y,
            col_width,
        ) - 1

    right_y = draw_paragraph(canvas, "How To Run", styles["section"], right_x, right_y, col_width) - 3
    for step in sections["how_to_run"]:
        right_y = draw_paragraph(
            canvas,
            step,
            styles["body"],
            right_x,
            right_y,
            col_width,
        ) - 1

    footer_y = 22 * mm
    draw_paragraph(
        canvas,
        sections["evidence"],
        styles["small"],
        left_x,
        footer_y,
        width - (2 * margin),
    )

    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.line(left_x, footer_y + 6, width - margin, footer_y + 6)
    canvas.showPage()
    canvas.save()
    return output_path


if __name__ == "__main__":
    path = build_pdf(OUTPUT_PATH)
    print(path)
