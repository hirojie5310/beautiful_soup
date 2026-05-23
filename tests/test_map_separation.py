from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


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


def make_scaled_map_from_tiles(
    tileset: np.ndarray,
    source_tile_size: int,
    target_tile_size: int,
    rows: int = 4,
    cols: int = 4,
) -> np.ndarray:
    source_map = make_map_from_tiles(tileset, tile_size=source_tile_size, rows=rows, cols=cols)
    scaled_map = np.zeros((rows * target_tile_size, cols * target_tile_size, source_map.shape[2]), dtype=np.uint8)
    for row in range(rows):
        for col in range(cols):
            source_y = row * source_tile_size
            source_x = col * source_tile_size
            tile = source_map[source_y : source_y + source_tile_size, source_x : source_x + source_tile_size]
            resized = map_separation.resize_tile(tile, target_tile_size)
            target_y = row * target_tile_size
            target_x = col * target_tile_size
            scaled_map[target_y : target_y + target_tile_size, target_x : target_x + target_tile_size] = resized
    return scaled_map


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


def test_find_tileset_bbox_prefers_stronger_search_candidate_over_anchored_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = np.zeros((160, 240, 4), dtype=np.uint8)
    image[:, :, 3] = 255
    map_bbox = map_separation.BoundingBox(left=0, top=0, right=64, bottom=64)
    anchored_bbox = map_separation.BoundingBox(left=120, top=16, right=520, bottom=216)
    search_bbox = map_separation.BoundingBox(left=132, top=40, right=388, bottom=168)

    monkeypatch.setattr(
        map_separation,
        "detect_layer1_tab_bbox",
        lambda *_args, **_kwargs: map_separation.BoundingBox(left=120, top=0, right=220, bottom=20),
    )
    monkeypatch.setattr(
        map_separation,
        "refine_anchored_tileset_bbox",
        lambda *_args, **_kwargs: anchored_bbox,
    )
    monkeypatch.setattr(
        map_separation,
        "trim_tileset_top_noncontent_rows",
        lambda _image, bbox, _tile_size: bbox,
    )
    monkeypatch.setattr(
        map_separation,
        "trim_tileset_bottom_neutral_rows",
        lambda _image, bbox, _tile_size: bbox,
    )
    monkeypatch.setattr(map_separation, "detect_tileset_top_boundary", lambda *_args, **_kwargs: 40)
    monkeypatch.setattr(map_separation, "find_first_run", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(map_separation, "find_last_run", lambda *_args, **_kwargs: 255)
    monkeypatch.setattr(map_separation, "detect_tileset_tile_size", lambda *_args, **_kwargs: 16)
    monkeypatch.setattr(
        map_separation,
        "build_tileset_candidate_bbox",
        lambda *_args, **_kwargs: search_bbox,
    )

    def fake_score_tileset_candidate_bbox(image_np, candidate_bbox, tile_size, map_np=None):
        if candidate_bbox == anchored_bbox:
            return -1000.0
        if candidate_bbox == search_bbox:
            return -100.0 if tile_size == 16 else -500.0
        raise AssertionError(f"Unexpected bbox scored: {candidate_bbox}")

    monkeypatch.setattr(
        map_separation,
        "score_tileset_candidate_bbox",
        fake_score_tileset_candidate_bbox,
    )

    bbox = map_separation.find_tileset_bbox(image, workspace_top=40, map_bbox=map_bbox)

    assert bbox == search_bbox


def test_refine_tileset_left_clamps_rough_left_that_exceeds_feasible_range() -> None:
    tile_size = 38
    crop_width = tile_size * map_separation.TILESET_COLUMNS
    crop_height = tile_size * map_separation.TILESET_ROWS
    search_width = crop_width + 92
    search_region = np.zeros((crop_height + 40, search_width, 3), dtype=np.uint8)

    refined_left = map_separation.refine_tileset_left(
        search_region,
        rough_left=188,
        tile_size=tile_size,
    )

    assert refined_left == 92


def test_extract_assets_from_screenshot_defaults_to_38px_tileset_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screenshot_path = Path("/tmp/screenshot.png")
    map_output_path = Path("/tmp/map.png")
    tileset_output_path = Path("/tmp/tileset.png")
    screenshot = Image.fromarray(np.zeros((420, 700, 4), dtype=np.uint8), mode="RGBA")
    map_bbox = map_separation.BoundingBox(left=0, top=0, right=32, bottom=32)
    tileset_bbox = map_separation.BoundingBox(left=40, top=58, right=40 + 16 * 38, bottom=58 + 8 * 38)
    seen_tile_sizes: list[int | None] = []

    monkeypatch.setattr(map_separation, "open_image", lambda _path: screenshot)
    monkeypatch.setattr(map_separation, "detect_workspace_top", lambda _image: 10)
    monkeypatch.setattr(map_separation, "find_map_canvas_bbox", lambda _image, _workspace_top: map_bbox)

    def fake_find_tileset_bbox(_image, _workspace_top, map_bbox=None, forced_tile_size=None):
        seen_tile_sizes.append(forced_tile_size)
        return tileset_bbox

    monkeypatch.setattr(map_separation, "find_tileset_bbox", fake_find_tileset_bbox)
    monkeypatch.setattr(
        map_separation,
        "refine_map_canvas_bbox",
        lambda _image, bbox, _tile_size, tileset_np=None: bbox,
    )

    _, _, extracted_map_bbox, extracted_tileset_bbox = map_separation.extract_assets_from_screenshot(
        screenshot_path=screenshot_path,
        map_output_path=map_output_path,
        tileset_output_path=tileset_output_path,
    )

    assert seen_tile_sizes == [38]
    assert extracted_map_bbox == map_bbox
    assert extracted_tileset_bbox == map_separation.BoundingBox(
        left=40,
        top=20,
        right=40 + 16 * 38,
        bottom=20 + 8 * 38,
    )


def test_shift_tileset_bbox_up_one_tile_respects_bounds() -> None:
    image = np.zeros((200, 300, 4), dtype=np.uint8)
    bbox = map_separation.BoundingBox(left=10, top=50, right=100, bottom=150)

    shifted = map_separation.shift_tileset_bbox_up_one_tile(image, bbox, tile_size=38)
    unchanged = map_separation.shift_tileset_bbox_up_one_tile(image, bbox, tile_size=60)

    assert shifted == map_separation.BoundingBox(left=10, top=12, right=100, bottom=112)
    assert unchanged == bbox


def test_shift_tileset_bbox_up_one_tile_keeps_bbox_when_added_band_is_ui_like() -> None:
    tile_size = 38
    image = np.zeros((220, 320, 4), dtype=np.uint8)
    image[:, :, 3] = 255
    bbox = map_separation.BoundingBox(left=20, top=56, right=20 + (tile_size * 16), bottom=56 + (tile_size * 8))

    image[18:56, bbox.left : bbox.right, :3] = (240, 240, 240)
    image[284:322, bbox.left : bbox.right, :3] = (30, 140, 80)

    shifted = map_separation.shift_tileset_bbox_up_one_tile(
        image,
        bbox,
        tile_size=tile_size,
        workspace_top=54,
    )

    assert shifted == bbox


def test_align_tileset_bbox_to_tab_left_trims_left_and_bottom(monkeypatch: pytest.MonkeyPatch) -> None:
    image = np.zeros((500, 3200, 4), dtype=np.uint8)
    image[:, :, 3] = 255
    candidate_bbox = map_separation.BoundingBox(left=2476, top=56, right=3084, bottom=360)
    tab_bbox = map_separation.BoundingBox(left=2572, top=0, right=2700, bottom=54)
    expected_bbox = map_separation.BoundingBox(left=2572, top=56, right=3084, bottom=312)

    aligned = map_separation.align_tileset_bbox_to_tab_left(image, candidate_bbox, tab_bbox)

    assert aligned == expected_bbox


def test_align_tileset_bbox_to_tab_left_re_refines_top_for_new_tile_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = np.zeros((500, 3200, 4), dtype=np.uint8)
    image[:, :, 3] = 255
    tab_bbox = map_separation.BoundingBox(left=2572, top=0, right=2700, bottom=54)
    candidate_bbox = map_separation.BoundingBox(left=2476, top=60, right=3084, bottom=364)
    expected_bbox = map_separation.BoundingBox(left=2572, top=56, right=3084, bottom=312)

    aligned = map_separation.align_tileset_bbox_to_tab_left(image, candidate_bbox, tab_bbox)

    assert aligned.top <= candidate_bbox.top
    assert aligned == expected_bbox


def test_analyze_map_resizes_tileset_tiles_to_map_tile_size(tmp_path: Path) -> None:
    tileset_tile_size = 8
    map_tile_size = 6
    tileset = make_tileset(tileset_tile_size)
    map_image = make_scaled_map_from_tiles(
        tileset,
        source_tile_size=tileset_tile_size,
        target_tile_size=map_tile_size,
        rows=4,
        cols=4,
    )

    tileset_path = tmp_path / "tileset.png"
    map_path = tmp_path / "scaled_map.png"
    Image.fromarray(np.concatenate([tileset, np.full((tileset.shape[0], tileset.shape[1], 1), 255, dtype=np.uint8)], axis=2)).save(tileset_path)
    Image.fromarray(np.concatenate([map_image, np.full((map_image.shape[0], map_image.shape[1], 1), 255, dtype=np.uint8)], axis=2)).save(map_path)

    summary = map_separation.analyze_map(
        map_path=map_path,
        tileset_path=tileset_path,
        map_offset_x=0,
        map_offset_y=0,
        map_tile_columns=None,
        map_tile_rows=None,
        map_tile_size=map_tile_size,
    )

    comparison = Image.open(summary["output_paths"]["comparison"]).convert("RGBA")
    comparison_np = np.array(comparison)
    half_width = comparison.width // 2

    assert summary["tile_size"] == map_tile_size
    assert summary["tileset_tile_size"] == tileset_tile_size
    assert np.array_equal(
        comparison_np[:, :half_width],
        comparison_np[:, half_width:],
    )


def test_find_tile_prefers_neighbor_connected_candidate_for_near_ties() -> None:
    tile_size = 6
    left_tile = np.full((tile_size, tile_size, 3), fill_value=30, dtype=np.uint8)

    chunk = np.full((tile_size, tile_size, 3), fill_value=140, dtype=np.uint8)
    chunk[1:-1, 1:-1] = 180
    chunk[:, 0, :] = 100

    first_tile = chunk.copy()
    first_tile[:, 0, :] = 70

    second_tile = chunk.copy()
    second_tile[:, 0, :] = 30

    chosen_tile_id, match_mode, _ = map_separation.find_tile(
        chunk,
        [first_tile, second_tile],
        left_tile=left_tile,
    )

    assert chosen_tile_id == 2
    assert match_mode == "inner_exact"


def test_find_tile_with_cached_features_matches_uncached_result() -> None:
    tile_size = 8
    tileset = make_tileset(tile_size)
    tiles = map_separation.split_tiles(tileset, tile_size)
    chunk = tiles[7].copy()
    left_tile = tiles[6]
    top_tile = tiles[1]
    tile_features = map_separation.build_tile_features(tiles)
    chunk_features = map_separation.build_chunk_features(
        chunk,
        left_tile=left_tile,
        top_tile=top_tile,
    )

    uncached = map_separation.find_tile(
        chunk,
        tiles,
        left_tile=left_tile,
        top_tile=top_tile,
    )
    cached = map_separation.find_tile(
        chunk,
        tiles,
        left_tile=left_tile,
        top_tile=top_tile,
        tile_features=tile_features,
    )
    fully_cached = map_separation.find_tile(
        chunk,
        tiles,
        left_tile=left_tile,
        top_tile=top_tile,
        tile_features=tile_features,
        chunk_features=chunk_features,
    )

    assert cached == uncached
    assert fully_cached == uncached
