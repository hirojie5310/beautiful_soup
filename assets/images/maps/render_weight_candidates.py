from __future__ import annotations

import csv
import colorsys
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent
MODULE_PATH = BASE_DIR / "map_separation.py"
SPEC = importlib.util.spec_from_file_location("map_separation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
map_separation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = map_separation
SPEC.loader.exec_module(map_separation)

MAP_PATH = BASE_DIR / "Saronia_NorthWest-Library_map.png"
TILESET_PATH = BASE_DIR / "TILESET" / "TILESET - CombinedUnique16px.png"
OUTPUT_IMAGE_PATH = BASE_DIR / "Saronia_NorthWest-Library_weight_candidates.png"
OUTPUT_CSV_PATH = BASE_DIR / "Saronia_NorthWest-Library_weight_candidates.csv"
GUIDE_CSV_PATH = BASE_DIR / "TILESET" / "TILESET - CombinedUnique16px.csv"
MAP_TILE_SIZE = 32
BOOKSHELF_POINTS = [(3, 5), (3, 6), (4, 5), (5, 5), (5, 6)]  # 1-based tile coords
TOP_K = 5
FOCUS_TILE_IDS = [394, 251]


@dataclass(frozen=True)
class WeightPreset:
    name: str
    center: float
    lower: float
    block: float
    edge: float
    profile: float
    color: float


PRESETS = [
    WeightPreset("balanced", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
    WeightPreset("center_x2", 2.0, 1.0, 1.0, 1.0, 1.0, 1.0),
    WeightPreset("lower_x2", 1.0, 2.0, 1.0, 0.8, 1.0, 1.0),
    WeightPreset("block_x2", 1.0, 1.5, 2.0, 1.0, 1.0, 1.0),
    WeightPreset("color_x2", 1.0, 1.5, 1.0, 1.0, 1.0, 2.0),
    WeightPreset("color_x4", 1.0, 1.5, 1.0, 0.8, 1.0, 4.0),
    WeightPreset("center_lower_color", 2.0, 2.0, 1.0, 0.8, 1.0, 3.0),
    WeightPreset("lower_color_profile", 1.0, 2.0, 1.0, 0.8, 2.0, 3.0),
]


@dataclass(frozen=True)
class ColorFeatures:
    mean_rgb: np.ndarray
    std_rgb: np.ndarray
    mean_hsv: np.ndarray


def build_color_features(tile: np.ndarray) -> ColorFeatures:
    comparable = map_separation.normalize_tile_for_comparison(tile)
    inner = comparable[1:-1, 1:-1, :]
    pixels = inner.reshape(-1, 3).astype(np.float32)
    rgb = pixels / 255.0
    hsv = np.array([colorsys.rgb_to_hsv(*pixel) for pixel in rgb], dtype=np.float32)
    return ColorFeatures(
        mean_rgb=pixels.mean(axis=0),
        std_rgb=pixels.std(axis=0),
        mean_hsv=(hsv * np.array([255.0, 255.0, 255.0], dtype=np.float32)).mean(axis=0),
    )


def color_distance(chunk_color: ColorFeatures, tile_color: ColorFeatures) -> int:
    mean_rgb_score = int(np.abs(chunk_color.mean_rgb - tile_color.mean_rgb).sum())
    std_rgb_score = int(np.abs(chunk_color.std_rgb - tile_color.std_rgb).sum())
    mean_hsv_score = int(np.abs(chunk_color.mean_hsv - tile_color.mean_hsv).sum())
    return mean_rgb_score + std_rgb_score + mean_hsv_score


def load_manifest() -> dict[int, dict[str, str]]:
    with GUIDE_CSV_PATH.open(newline="", encoding="utf-8") as handle:
        return {int(row["tile_id"]) + 1: row for row in csv.DictReader(handle)}


def weighted_find_tiles(
    chunk_features: map_separation.ChunkFeatures,
    tile_features: list[map_separation.TileFeatures],
    chunk_color: ColorFeatures,
    tile_colors: list[ColorFeatures],
    preset: WeightPreset,
) -> list[tuple[int, int]]:
    scored_tiles: list[tuple[int, int]] = []
    for index, feature in enumerate(tile_features):
        inner_score = int(np.abs(chunk_features.inner_chunk_i32 - feature.inner_tile_i32).sum())
        center_score = int(np.abs(chunk_features.center_block_signature - feature.center_block_signature).sum())
        lower_score = int(np.abs(chunk_features.lower_block_signature - feature.lower_block_signature).sum())
        block_score = int(np.abs(chunk_features.block_signature - feature.block_signature).sum())
        edge_score = int(np.abs(chunk_features.inner_edge_view - feature.inner_edge_view).sum())
        profile_score = int(
            np.abs(chunk_features.col_signature - feature.col_signature).sum()
            + np.abs(chunk_features.row_signature - feature.row_signature).sum()
        )
        color_score = color_distance(chunk_color, tile_colors[index])
        weighted_score = (
            inner_score
            + (center_score * preset.center)
            + (lower_score * preset.lower)
            + (block_score * preset.block)
            + (edge_score * preset.edge)
            + (profile_score * preset.profile)
            + (color_score * preset.color)
        )
        scored_tiles.append((index + 1, int(round(weighted_score))))
    scored_tiles.sort(key=lambda item: (item[1], item[0]))
    return scored_tiles


def main() -> None:
    map_img = Image.open(MAP_PATH).convert("RGBA")
    map_np = np.array(map_img)[:, :, :3]
    tileset_img = Image.open(TILESET_PATH).convert("RGBA")
    tileset_np = np.array(tileset_img)[:, :, :3]
    tileset_tile_size = map_separation.infer_tile_size(tileset_np)
    tiles = map_separation.build_map_tiles(tileset_np, tileset_tile_size=tileset_tile_size, map_tile_size=MAP_TILE_SIZE)
    tile_features = map_separation.build_tile_features(tiles)
    tile_colors = [build_color_features(tile) for tile in tiles]
    manifest = load_manifest()

    chosen_rows: list[dict[str, str]] = []
    preview_cell = 84
    header_height = 20
    point_group_width = preview_cell * TOP_K
    canvas = Image.new(
        "RGBA",
        (point_group_width * len(BOOKSHELF_POINTS) + 160, (preview_cell + header_height) * (len(PRESETS) + 1)),
        (255, 255, 255, 255),
    )
    draw = ImageDraw.Draw(canvas)

    for point_index, (tile_y, tile_x) in enumerate(BOOKSHELF_POINTS, start=1):
        source_tile = map_img.crop(
            (
                (tile_x - 1) * MAP_TILE_SIZE,
                (tile_y - 1) * MAP_TILE_SIZE,
                tile_x * MAP_TILE_SIZE,
                tile_y * MAP_TILE_SIZE,
            )
        ).resize((64, 64), Image.Resampling.NEAREST)
        group_left = 160 + ((point_index - 1) * point_group_width)
        canvas.paste(source_tile, (group_left + 10, 8))
        draw.text((group_left + 2, 74), f"({tile_y},{tile_x})", fill=(0, 0, 0, 255))
        for rank in range(1, TOP_K + 1):
            draw.text((group_left + ((rank - 1) * preview_cell) + 22, 74), f"#{rank}", fill=(0, 0, 0, 255))

    draw.text((8, 74), "source", fill=(0, 0, 0, 255))

    for preset_index, preset in enumerate(PRESETS, start=1):
        row_top = preset_index * (preview_cell + header_height)
        draw.text(
            (4, row_top + 4),
            f"{preset.name} c={preset.center:g} l={preset.lower:g} b={preset.block:g} e={preset.edge:g} p={preset.profile:g} col={preset.color:g}",
            fill=(0, 0, 0, 255),
        )
        csv_row = {
            "preset": preset.name,
            "center": str(preset.center),
            "lower": str(preset.lower),
            "block": str(preset.block),
            "edge": str(preset.edge),
            "profile": str(preset.profile),
            "color": str(preset.color),
        }
        for point_index, (tile_y, tile_x) in enumerate(BOOKSHELF_POINTS, start=1):
            chunk = map_np[
                (tile_y - 1) * MAP_TILE_SIZE : tile_y * MAP_TILE_SIZE,
                (tile_x - 1) * MAP_TILE_SIZE : tile_x * MAP_TILE_SIZE,
            ]
            chunk_features = map_separation.build_chunk_features(chunk)
            chunk_color = build_color_features(chunk)
            ranked_tiles = weighted_find_tiles(chunk_features, tile_features, chunk_color, tile_colors, preset)
            group_left = 160 + ((point_index - 1) * point_group_width)
            rank_lookup = {tile_id: rank for rank, (tile_id, _) in enumerate(ranked_tiles, start=1)}
            for focus_tile_id in FOCUS_TILE_IDS:
                csv_row[f"rank_{focus_tile_id}_{tile_y}_{tile_x}"] = str(rank_lookup.get(focus_tile_id, ""))

            for rank, (tile_id, score) in enumerate(ranked_tiles[:TOP_K], start=1):
                csv_row[f"tile_{tile_y}_{tile_x}_rank_{rank}"] = str(tile_id)
                csv_row[f"score_{tile_y}_{tile_x}_rank_{rank}"] = str(score)

                atlas_row = int(manifest[tile_id]["atlas_row"])
                atlas_col = int(manifest[tile_id]["atlas_column"])
                tile = tileset_img.crop(
                    (
                        atlas_col * 16,
                        atlas_row * 16,
                        (atlas_col + 1) * 16,
                        (atlas_row + 1) * 16,
                    )
                ).resize((64, 64), Image.Resampling.NEAREST)
                left = group_left + ((rank - 1) * preview_cell) + 10
                canvas.paste(tile, (left, row_top + 8))
                draw.text((left - 4, row_top + 74), f"id {tile_id}", fill=(0, 0, 0, 255))
        chosen_rows.append(csv_row)

    with OUTPUT_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(chosen_rows[0].keys()))
        writer.writeheader()
        writer.writerows(chosen_rows)

    canvas.save(OUTPUT_IMAGE_PATH)
    print(OUTPUT_IMAGE_PATH)
    print(OUTPUT_CSV_PATH)


if __name__ == "__main__":
    main()
