from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw

TILE_SIZE = 16
PREVIEW_SCALE = 3
CELL_PADDING = 18
FONT_COLOR = (0, 0, 0, 255)
BG_COLOR = (255, 255, 255, 255)
GRID_COLOR = (210, 210, 210, 255)

BASE_DIR = Path(__file__).resolve().parent
TILESET_PATH = BASE_DIR / "TILESET" / "TILESET - CombinedUnique16px.png"
MANIFEST_PATH = BASE_DIR / "TILESET" / "TILESET - CombinedUnique16px.csv"
OUTPUT_PATH = BASE_DIR / "TILESET" / "TILESET - CombinedUnique16px.guide.png"


def load_manifest_rows() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    tileset = Image.open(TILESET_PATH).convert("RGBA")
    rows = load_manifest_rows()
    atlas_rows = max(int(row["atlas_row"]) for row in rows) + 1
    atlas_columns = max(int(row["atlas_column"]) for row in rows) + 1

    preview_tile = TILE_SIZE * PREVIEW_SCALE
    cell_width = preview_tile + (CELL_PADDING * 2)
    cell_height = preview_tile + 32
    canvas = Image.new("RGBA", (atlas_columns * cell_width, atlas_rows * cell_height), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    for row in rows:
        atlas_row = int(row["atlas_row"])
        atlas_column = int(row["atlas_column"])
        tile_id = int(row["tile_id"])
        left = atlas_column * cell_width
        top = atlas_row * cell_height
        tile = tileset.crop(
            (
                atlas_column * TILE_SIZE,
                atlas_row * TILE_SIZE,
                (atlas_column + 1) * TILE_SIZE,
                (atlas_row + 1) * TILE_SIZE,
            )
        ).resize((preview_tile, preview_tile), Image.Resampling.NEAREST)
        canvas.paste(tile, (left + CELL_PADDING, top + 4))
        draw.rectangle(
            (left, top, left + cell_width - 1, top + cell_height - 1),
            outline=GRID_COLOR,
            width=1,
        )
        draw.text(
            (left + 4, top + preview_tile + 6),
            f"r{atlas_row + 1} c{atlas_column + 1}",
            fill=FONT_COLOR,
        )
        draw.text(
            (left + 4, top + preview_tile + 18),
            f"csv {tile_id} / map {tile_id + 1}",
            fill=FONT_COLOR,
        )

    canvas.save(OUTPUT_PATH)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
