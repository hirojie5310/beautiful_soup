from pathlib import Path
import csv

import numpy as np
from PIL import Image

TILE_SIZE = 24
INNER_MARGIN = 1
SUSPICIOUS_SCORE_THRESHOLD = 500
INNER_SCORE_TIE_THRESHOLD = 32
MAP_OFFSET_X = 0    # Floating Continents: 10
MAP_OFFSET_Y = 0    # Floating Continents: 5
MAP_TILE_COLUMNS = None
MAP_TILE_ROWS = None
BASE_DIR = Path(__file__).resolve().parent
TILESET_PATH = BASE_DIR / "TILESET - SealedCave.png"
MAP_PATH = BASE_DIR / "Sealed_Cave_B2_2.png"
RECONSTRUCTED_PATH = BASE_DIR / "Sealed_Cave_B2_2_reconstructed.png"
COMPARISON_PATH = BASE_DIR / "Sealed_Cave_B2_2_comparison.png"
CSV_PATH = BASE_DIR / "Sealed_Cave_B2_2_tiles.csv"
DEBUG_CSV_PATH = BASE_DIR / "Sealed_Cave_B2_2_tiles_debug.csv"
SUSPICIOUS_PATH = BASE_DIR / "Sealed_Cave_B2_2_suspicious_tiles.png"


def open_image(path: Path) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")
    return Image.open(path)


tileset = open_image(TILESET_PATH)
map_img = open_image(MAP_PATH)

# タイルセット分割
tiles = []
tileset_np = np.array(tileset)

h, w = tileset_np.shape[:2]
for y in range(0, h, TILE_SIZE):
    for x in range(0, w, TILE_SIZE):
        tile = tileset_np[y : y + TILE_SIZE, x : x + TILE_SIZE]
        if tile.shape[:2] != (TILE_SIZE, TILE_SIZE):
            continue
        tiles.append(tile)


def inner_view(tile: np.ndarray, margin: int = INNER_MARGIN) -> np.ndarray:
    if margin <= 0:
        return tile
    return tile[margin:-margin, margin:-margin, :]


def find_tile(chunk: np.ndarray) -> tuple[int, str, int]:
    inner_chunk = inner_view(chunk)

    scored_tiles = []
    for index, tile in enumerate(tiles):
        if tile.shape != chunk.shape:
            continue
        diff = inner_chunk.astype(np.int32) - inner_view(tile).astype(np.int32)
        inner_score = int(np.abs(diff).sum())
        full_diff = chunk.astype(np.int32) - tile.astype(np.int32)
        full_score = int(np.abs(full_diff).sum())
        scored_tiles.append((index + 1, inner_score, full_score))

    if not scored_tiles:
        raise ValueError(f"No valid tiles found for chunk shape {chunk.shape}")

    scored_tiles.sort(key=lambda item: (item[1], item[2], item[0]))
    best_inner_score = scored_tiles[0][1]
    near_ties = [
        item for item in scored_tiles if item[1] <= best_inner_score + INNER_SCORE_TIE_THRESHOLD
    ]
    chosen_tile_id, chosen_inner_score, _ = min(near_ties, key=lambda item: (item[2], item[1], item[0]))
    match_mode = "inner_exact" if chosen_inner_score == 0 else "nearest"
    return chosen_tile_id, match_mode, chosen_inner_score


# マップ分割
source_map_np = np.array(map_img)
source_mh, source_mw = source_map_np.shape[:2]
available_columns = (source_mw - MAP_OFFSET_X) // TILE_SIZE
available_rows = (source_mh - MAP_OFFSET_Y) // TILE_SIZE
tile_columns = MAP_TILE_COLUMNS if MAP_TILE_COLUMNS is not None else available_columns
tile_rows = MAP_TILE_ROWS if MAP_TILE_ROWS is not None else available_rows
tile_columns = min(tile_columns, available_columns)
tile_rows = min(tile_rows, available_rows)
cropped_width = tile_columns * TILE_SIZE
cropped_height = tile_rows * TILE_SIZE
map_np = source_map_np[
    MAP_OFFSET_Y : MAP_OFFSET_Y + cropped_height,
    MAP_OFFSET_X : MAP_OFFSET_X + cropped_width,
]
mh, mw = map_np.shape[:2]

result = []
debug_rows = []
reconstructed_rows = []

for y in range(0, mh, TILE_SIZE):
    row = []
    debug_row = []
    reconstructed_row = []
    for x in range(0, mw, TILE_SIZE):
        chunk = map_np[y : y + TILE_SIZE, x : x + TILE_SIZE]
        tile_id, match_mode, score = find_tile(chunk)
        row.append(tile_id)
        debug_row.append(
            {
                "tile_id": tile_id,
                "mode": match_mode,
                "score": score,
            }
        )
        reconstructed_row.append(tiles[tile_id - 1])
    result.append(row)
    debug_rows.append(debug_row)
    reconstructed_rows.append(reconstructed_row)

reconstructed = np.zeros_like(map_np)
for row_index, reconstructed_row in enumerate(reconstructed_rows):
    for column_index, tile in enumerate(reconstructed_row):
        y = row_index * TILE_SIZE
        x = column_index * TILE_SIZE
        reconstructed[y : y + TILE_SIZE, x : x + TILE_SIZE] = tile

reconstructed_img = Image.fromarray(reconstructed)
reconstructed_img.save(RECONSTRUCTED_PATH)

cropped_map_img = Image.fromarray(map_np)
comparison = Image.new("RGBA", (cropped_map_img.width * 2, cropped_map_img.height), (0, 0, 0, 255))
comparison.paste(cropped_map_img, (0, 0))
comparison.paste(reconstructed_img, (cropped_map_img.width, 0))
comparison.save(COMPARISON_PATH)

with CSV_PATH.open("w", newline="", encoding="utf-8") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerows(result)

with DEBUG_CSV_PATH.open("w", newline="", encoding="utf-8") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(["row", "col", "tile_id", "mode", "score"])
    for row_index, row in enumerate(debug_rows):
        for col_index, cell in enumerate(row):
            writer.writerow(
                [
                    row_index,
                    col_index,
                    cell["tile_id"],
                    cell["mode"],
                    cell["score"],
                ]
            )

suspicious_img = cropped_map_img.copy()
suspicious_overlay = Image.new("RGBA", cropped_map_img.size, (0, 0, 0, 0))
suspicious_np = np.array(suspicious_overlay)
for row_index, row in enumerate(debug_rows):
    for col_index, cell in enumerate(row):
        if cell["mode"] != "nearest" or cell["score"] < SUSPICIOUS_SCORE_THRESHOLD:
            continue
        y = row_index * TILE_SIZE
        x = col_index * TILE_SIZE
        suspicious_np[y : y + TILE_SIZE, x : x + TILE_SIZE] = np.array([255, 0, 0, 96], dtype=np.uint8)

suspicious_overlay = Image.fromarray(suspicious_np, mode="RGBA")
suspicious_img.alpha_composite(suspicious_overlay)
suspicious_img.save(SUSPICIOUS_PATH)

# 配列出力
for row in result:
    print(row)

print()
print("# debug")
for row in debug_rows:
    print(
        [
            f"{cell['tile_id']}:{cell['mode']}:{cell['score']}"
            for cell in row
        ]
    )

print()
print(f"# reconstructed_image: {RECONSTRUCTED_PATH}")
print(f"# comparison_image: {COMPARISON_PATH}")
print(f"# csv: {CSV_PATH}")
print(f"# debug_csv: {DEBUG_CSV_PATH}")
print(f"# suspicious_tiles_image: {SUSPICIOUS_PATH}")
