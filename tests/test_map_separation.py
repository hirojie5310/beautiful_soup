from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).resolve().parents[1] / "assets" / "images" / "maps" / "map_separation.py"
SPEC = importlib.util.spec_from_file_location("map_separation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
map_separation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = map_separation
SPEC.loader.exec_module(map_separation)


def make_tileset(tile_size: int = 8) -> np.ndarray:
    height = tile_size * map_separation.TILESET_ROWS
    width = tile_size * map_separation.TILESET_COLUMNS
    tileset = np.zeros((height, width, 3), dtype=np.uint8)

    for row in range(map_separation.TILESET_ROWS):
        for col in range(map_separation.TILESET_COLUMNS):
            base_y = row * tile_size
            base_x = col * tile_size
            color = np.array(
                [
                    30 + (col * 11) % 180,
                    40 + (row * 19) % 170,
                    50 + ((row + col) * 13) % 160,
                ],
                dtype=np.uint8,
            )
            tileset[base_y : base_y + tile_size, base_x : base_x + tile_size] = color
            inner_color = np.clip(
                color.astype(np.int16) + np.array([20, 10, 15], dtype=np.int16),
                0,
                255,
            ).astype(np.uint8)
            tileset[base_y + 1 : base_y + tile_size - 1, base_x + 1 : base_x + tile_size - 1] = inner_color
    return tileset


def make_map_from_tiles(tileset: np.ndarray, tile_size: int = 8, rows: int = 4, cols: int = 4) -> np.ndarray:
    tiles = map_separation.split_tiles(tileset, tile_size)
    map_image = np.zeros((rows * tile_size, cols * tile_size, 3), dtype=np.uint8)

    for row in range(rows):
        for col in range(cols):
            tile = tiles[(row * 5 + col * 7) % len(tiles)]
            base_y = row * tile_size
            base_x = col * tile_size
            map_image[base_y : base_y + tile_size, base_x : base_x + tile_size] = tile
    return map_image


def test_refine_map_canvas_prefers_tileset_matching_component() -> None:
    tile_size = 8
    tileset = make_tileset(tile_size)
    map_image = make_map_from_tiles(tileset, tile_size=tile_size)

    sidebar = np.full((map_image.shape[0], 24, 3), fill_value=(76, 76, 76), dtype=np.uint8)
    gutter = np.zeros((map_image.shape[0], tile_size, 3), dtype=np.uint8)
    image = np.concatenate([sidebar, gutter, map_image], axis=1)
    image_rgba = np.concatenate(
        [image, np.full((image.shape[0], image.shape[1], 1), fill_value=255, dtype=np.uint8)],
        axis=2,
    )

    rough_bbox = map_separation.BoundingBox(left=0, top=0, right=image.shape[1], bottom=image.shape[0])
    refined_bbox = map_separation.refine_map_canvas_bbox(
        image_rgba,
        rough_bbox,
        tile_size,
        tileset_np=tileset,
    )

    assert refined_bbox.left == sidebar.shape[1] + gutter.shape[1]
    assert refined_bbox.top == 0
    assert refined_bbox.width == map_image.shape[1]
    assert refined_bbox.height == map_image.shape[0]


def test_trim_map_component_preserves_full_height_grass_columns() -> None:
    tile_size = 8
    map_region = np.full((tile_size * 4, tile_size * 4, 3), fill_value=(40, 114, 0), dtype=np.uint8)
    content_mask = np.ones((tile_size * 4, tile_size * 4), dtype=bool)
    component_bbox = map_separation.BoundingBox(left=0, top=0, right=tile_size * 4, bottom=tile_size * 4)

    trimmed_bbox = map_separation.trim_map_component_bbox(
        map_region,
        content_mask,
        component_bbox,
        tile_size,
    )

    assert trimmed_bbox is not None
    assert trimmed_bbox.left == 0
    assert trimmed_bbox.right == tile_size * 4


def test_refine_anchored_tileset_bbox_avoids_gray_bottom() -> None:
    tile_size = 8
    tileset = make_tileset(tile_size)
    map_image = make_map_from_tiles(tileset, tile_size=tile_size)

    gray_rows = np.full((3, tileset.shape[1], 3), fill_value=(76, 76, 76), dtype=np.uint8)
    screenshot_rgb = np.concatenate([tileset, gray_rows], axis=0)
    screenshot_rgba = np.concatenate(
        [screenshot_rgb, np.full((screenshot_rgb.shape[0], screenshot_rgb.shape[1], 1), fill_value=255, dtype=np.uint8)],
        axis=2,
    )

    refined_bbox = map_separation.refine_anchored_tileset_bbox(
        screenshot_rgba,
        anchor_left=0,
        anchor_top=3,
        tile_size=tile_size,
    )
    trimmed_bbox = map_separation.trim_tileset_bottom_neutral_rows(screenshot_rgba, refined_bbox, tile_size)

    assert refined_bbox is not None
    assert trimmed_bbox.top == 0
    assert trimmed_bbox.bottom == tileset.shape[0]


def test_trim_tileset_top_noncontent_rows_avoids_light_border() -> None:
    tile_size = 8
    tileset = make_tileset(tile_size)

    bright_row = np.full((1, tileset.shape[1], 3), fill_value=(240, 240, 240), dtype=np.uint8)
    screenshot_rgb = np.concatenate([bright_row, tileset], axis=0)
    screenshot_rgba = np.concatenate(
        [screenshot_rgb, np.full((screenshot_rgb.shape[0], screenshot_rgb.shape[1], 1), fill_value=255, dtype=np.uint8)],
        axis=2,
    )

    candidate_bbox = map_separation.BoundingBox(
        left=0,
        top=0,
        right=tileset.shape[1],
        bottom=tileset.shape[0],
    )
    trimmed_bbox = map_separation.trim_tileset_top_noncontent_rows(
        screenshot_rgba,
        candidate_bbox,
        tile_size,
    )

    assert trimmed_bbox.top == 1
    assert trimmed_bbox.bottom == tileset.shape[0] + 1


def test_refine_map_canvas_merges_multiple_matching_components() -> None:
    tile_size = 8
    tileset = make_tileset(tile_size)
    left_map = make_map_from_tiles(tileset, tile_size=tile_size, rows=4, cols=3)
    right_map = make_map_from_tiles(tileset, tile_size=tile_size, rows=4, cols=3)

    gap = np.zeros((left_map.shape[0], tile_size * 2, 3), dtype=np.uint8)
    screenshot_rgb = np.concatenate([left_map, gap, right_map], axis=1)
    screenshot_rgba = np.concatenate(
        [
            screenshot_rgb,
            np.full((screenshot_rgb.shape[0], screenshot_rgb.shape[1], 1), fill_value=255, dtype=np.uint8),
        ],
        axis=2,
    )

    rough_bbox = map_separation.BoundingBox(left=0, top=0, right=screenshot_rgb.shape[1], bottom=screenshot_rgb.shape[0])
    refined_bbox = map_separation.refine_map_canvas_bbox(
        screenshot_rgba,
        rough_bbox,
        tile_size,
        tileset_np=tileset,
    )

    assert refined_bbox.left == 0
    assert refined_bbox.top == 0
    assert refined_bbox.right == screenshot_rgb.shape[1]
    assert refined_bbox.bottom == screenshot_rgb.shape[0]


def test_refine_map_canvas_ignores_single_tile_furniture_match() -> None:
    tile_size = 8
    tileset = make_tileset(tile_size)
    room_map = make_map_from_tiles(tileset, tile_size=tile_size, rows=4, cols=4)
    chair_tile = room_map[:tile_size, :tile_size].copy()

    gap = np.zeros((room_map.shape[0], tile_size * 2, 3), dtype=np.uint8)
    chair_block = np.zeros_like(room_map)
    chair_block[:tile_size, :tile_size] = chair_tile
    screenshot_rgb = np.concatenate([room_map, gap, chair_block], axis=1)
    screenshot_rgba = np.concatenate(
        [
            screenshot_rgb,
            np.full((screenshot_rgb.shape[0], screenshot_rgb.shape[1], 1), fill_value=255, dtype=np.uint8),
        ],
        axis=2,
    )

    rough_bbox = map_separation.BoundingBox(left=0, top=0, right=screenshot_rgb.shape[1], bottom=screenshot_rgb.shape[0])
    refined_bbox = map_separation.refine_map_canvas_bbox(
        screenshot_rgba,
        rough_bbox,
        tile_size,
        tileset_np=tileset,
    )

    assert refined_bbox.left == 0
    assert refined_bbox.top == 0
    assert refined_bbox.width == room_map.shape[1]
    assert refined_bbox.height == room_map.shape[0]


def test_refine_map_canvas_ignores_small_multi_tile_furniture_match() -> None:
    tile_size = 8
    tileset = make_tileset(tile_size)
    room_map = make_map_from_tiles(tileset, tile_size=tile_size, rows=5, cols=5)
    noisy_room = np.clip(room_map.astype(np.int16) + 1, 0, 255).astype(np.uint8)

    furniture_block = room_map[: tile_size * 2, : tile_size * 2].copy()
    gap = np.zeros((room_map.shape[0], tile_size * 2, 3), dtype=np.uint8)
    furniture_canvas = np.zeros_like(room_map)
    furniture_canvas[: furniture_block.shape[0], : furniture_block.shape[1]] = furniture_block

    screenshot_rgb = np.concatenate([noisy_room, gap, furniture_canvas], axis=1)
    screenshot_rgba = np.concatenate(
        [
            screenshot_rgb,
            np.full((screenshot_rgb.shape[0], screenshot_rgb.shape[1], 1), fill_value=255, dtype=np.uint8),
        ],
        axis=2,
    )

    rough_bbox = map_separation.BoundingBox(left=0, top=0, right=screenshot_rgb.shape[1], bottom=screenshot_rgb.shape[0])
    refined_bbox = map_separation.refine_map_canvas_bbox(
        screenshot_rgba,
        rough_bbox,
        tile_size,
        tileset_np=tileset,
    )

    assert refined_bbox.left == 0
    assert refined_bbox.top == 0
    assert refined_bbox.width == room_map.shape[1]
    assert refined_bbox.height == room_map.shape[0]


def test_trim_map_component_keeps_partial_right_wall_tile() -> None:
    tile_size = 8
    width = tile_size * 4
    height = tile_size * 3
    map_region = np.zeros((height, width, 3), dtype=np.uint8)
    content_mask = np.zeros((height, width), dtype=bool)
    content_mask[:, : width - 2] = True
    component_bbox = map_separation.BoundingBox(left=0, top=0, right=width - 2, bottom=height)

    trimmed_bbox = map_separation.trim_map_component_bbox(
        map_region,
        content_mask,
        component_bbox,
        tile_size,
    )

    assert trimmed_bbox is not None
    assert trimmed_bbox.width == tile_size * 4


def test_bbox_omits_significant_content_detects_missing_right_wall() -> None:
    content_mask = np.zeros((8, 8), dtype=bool)
    content_mask[:, 6:8] = True
    outer_bbox = map_separation.BoundingBox(left=0, top=0, right=8, bottom=8)
    inner_bbox = map_separation.BoundingBox(left=0, top=0, right=6, bottom=8)

    assert map_separation.bbox_omits_significant_content(
        content_mask,
        outer_bbox,
        inner_bbox,
        row_threshold=4,
        col_threshold=2,
    )


def test_trim_map_component_keeps_light_bottom_wall() -> None:
    tile_size = 8
    width = tile_size * 4
    height = tile_size * 4
    map_region = np.zeros((height, width, 3), dtype=np.uint8)
    map_region[: tile_size * 3, :] = (40, 114, 0)
    map_region[tile_size * 3 :, :] = (220, 222, 220)

    content_mask = np.zeros((height, width), dtype=bool)
    content_mask[: tile_size * 3, :] = True
    component_bbox = map_separation.BoundingBox(left=0, top=0, right=width, bottom=tile_size * 3)

    trimmed_bbox = map_separation.trim_map_component_bbox(
        map_region,
        content_mask,
        component_bbox,
        tile_size,
    )

    assert trimmed_bbox is not None
    assert trimmed_bbox.height == tile_size * 4


def test_trim_map_component_extends_through_multiple_bottom_tiles() -> None:
    tile_size = 8
    width = tile_size * 4
    height = tile_size * 5
    map_region = np.zeros((height, width, 3), dtype=np.uint8)
    map_region[: tile_size * 3, :] = (40, 114, 0)
    map_region[tile_size * 3 : tile_size * 4, :] = (220, 222, 220)
    map_region[tile_size * 4 :, : width // 2] = (160, 160, 160)

    content_mask = np.zeros((height, width), dtype=bool)
    content_mask[: tile_size * 3, :] = True
    component_bbox = map_separation.BoundingBox(left=0, top=0, right=width, bottom=tile_size * 3)

    trimmed_bbox = map_separation.trim_map_component_bbox(
        map_region,
        content_mask,
        component_bbox,
        tile_size,
    )

    assert trimmed_bbox is not None
    assert trimmed_bbox.height == tile_size * 5


def test_detect_layer1_tab_bbox_ignores_blue_preview_content() -> None:
    height = 120
    width = 700
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, 3] = 255

    panel_left = width - map_separation.TILESET_SEARCH_WIDTH
    workspace_top = 56

    image[:workspace_top, panel_left + 12 : panel_left + 140, :3] = (20, 120, 240)
    image[workspace_top + 2 : workspace_top + 34, panel_left + 320 : panel_left + 352, :3] = (20, 120, 240)

    tab_bbox = map_separation.detect_layer1_tab_bbox(image, workspace_top)

    assert tab_bbox.left == panel_left + 12
    assert tab_bbox.top == 0
    assert tab_bbox.right == panel_left + 140
    assert tab_bbox.bottom == workspace_top
