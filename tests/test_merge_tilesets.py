from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "assets" / "images" / "maps" / "merge_tilesets.py"
SPEC = importlib.util.spec_from_file_location("merge_tilesets", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
merge_tilesets = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = merge_tilesets
SPEC.loader.exec_module(merge_tilesets)


def make_tileset(path: Path, tile_pixel_size: int, tile_color_fn) -> None:
    image = Image.new(
        "RGBA",
        (
            merge_tilesets.TILESET_COLUMNS * tile_pixel_size,
            merge_tilesets.TILESET_ROWS * tile_pixel_size,
        ),
        (0, 0, 0, 0),
    )
    for row in range(merge_tilesets.TILESET_ROWS):
        for column in range(merge_tilesets.TILESET_COLUMNS):
            color = tile_color_fn(row, column)
            tile = Image.new("RGBA", (tile_pixel_size, tile_pixel_size), color)
            image.paste(tile, (column * tile_pixel_size, row * tile_pixel_size))
    image.save(path)


def unique_color(row: int, column: int) -> tuple[int, int, int, int]:
    index = row * merge_tilesets.TILESET_COLUMNS + column
    return (index, 255 - index, (index * 3) % 256, 255)


def test_deduplicate_tiles_normalizes_different_source_sizes(tmp_path: Path) -> None:
    source_dir = tmp_path / "TILESET"
    source_dir.mkdir()
    excluded_name = "TILESET - FloatingContinent.png"

    make_tileset(
        source_dir / "TILESET - Small.png",
        tile_pixel_size=2,
        tile_color_fn=unique_color,
    )
    make_tileset(
        source_dir / "TILESET - Large.png",
        tile_pixel_size=4,
        tile_color_fn=unique_color,
    )
    make_tileset(
        source_dir / excluded_name,
        tile_pixel_size=4,
        tile_color_fn=lambda row, column: (255, 0, 0, 255),
    )

    representatives, mappings = merge_tilesets.deduplicate_tiles(
        source_dir=source_dir,
        excluded_name=excluded_name,
        tile_size=16,
        pixel_diff_threshold=0.5,
    )

    assert len(representatives) == merge_tilesets.TILESET_COLUMNS * merge_tilesets.TILESET_ROWS
    assert len(mappings) == merge_tilesets.TILESET_COLUMNS * merge_tilesets.TILESET_ROWS * 2
    assert all(record.tile.size == (16, 16) for record in representatives)
    assert all(record.source_path.name != excluded_name for record in representatives)
    assert any(mapping.match_type == "exact" for mapping in mappings)


def test_build_output_image_uses_16_columns_layout(tmp_path: Path) -> None:
    source_dir = tmp_path / "TILESET"
    source_dir.mkdir()

    make_tileset(
        source_dir / "TILESET - Unique.png",
        tile_pixel_size=2,
        tile_color_fn=unique_color,
    )

    representatives, _ = merge_tilesets.deduplicate_tiles(
        source_dir=source_dir,
        excluded_name="does-not-exist.png",
        tile_size=16,
        pixel_diff_threshold=0.5,
    )
    output = merge_tilesets.build_output_image(representatives, tile_size=16)

    assert output.size == (16 * 16, 8 * 16)


def test_deduplicate_tiles_merges_near_identical_tiles(tmp_path: Path) -> None:
    source_dir = tmp_path / "TILESET"
    source_dir.mkdir()

    base_color = (32, 64, 128, 255)
    variant_color = (33, 64, 128, 255)

    make_tileset(
        source_dir / "TILESET - Base.png",
        tile_pixel_size=2,
        tile_color_fn=lambda row, column: base_color,
    )
    make_tileset(
        source_dir / "TILESET - Variant.png",
        tile_pixel_size=2,
        tile_color_fn=lambda row, column: variant_color if (row, column) == (0, 0) else base_color,
    )

    representatives, mappings = merge_tilesets.deduplicate_tiles(
        source_dir=source_dir,
        excluded_name="does-not-exist.png",
        tile_size=16,
        pixel_diff_threshold=0.5,
    )

    assert len(representatives) == 1
    fuzzy_mappings = [mapping for mapping in mappings if mapping.match_type == "fuzzy"]
    assert fuzzy_mappings
    assert fuzzy_mappings[0].record.source_path.name == "TILESET - Variant.png"


def test_reorder_tiles_by_similarity_remaps_tile_ids() -> None:
    bright_tile = Image.new("RGBA", (16, 16), (220, 220, 220, 255))
    dark_tile = Image.new("RGBA", (16, 16), (16, 16, 16, 255))
    representatives = [
        merge_tilesets.TileRecord(Path("bright.png"), 0, 0, bright_tile),
        merge_tilesets.TileRecord(Path("dark.png"), 0, 1, dark_tile),
    ]
    mappings = [
        merge_tilesets.TileMapping(tile_id=0, match_type="representative", record=representatives[0]),
        merge_tilesets.TileMapping(tile_id=1, match_type="representative", record=representatives[1]),
    ]

    reordered_representatives, reordered_mappings = merge_tilesets.reorder_tiles_by_similarity(
        representatives,
        mappings,
    )

    assert reordered_representatives[0].source_path.name == "dark.png"
    assert reordered_representatives[1].source_path.name == "bright.png"
    assert reordered_mappings[0].tile_id == 1
    assert reordered_mappings[1].tile_id == 0


def test_canonicalize_tile_for_matching_removes_single_pixel_noise() -> None:
    clean = Image.new("RGBA", (16, 16), (0, 0, 0, 255))
    noisy = clean.copy()
    noisy.putpixel((8, 8), (255, 0, 0, 255))

    canonical_clean = merge_tilesets.canonicalize_tile_for_matching(clean)
    canonical_noisy = merge_tilesets.canonicalize_tile_for_matching(noisy)

    assert canonical_clean.tobytes() == canonical_noisy.tobytes()


def test_canonicalize_tile_for_matching_ignores_one_pixel_edge_noise() -> None:
    clean = Image.new("RGBA", (16, 16), (20, 20, 20, 255))
    noisy = clean.copy()
    for row in range(16):
        noisy.putpixel((0, row), (255, 0, 0, 255))
    for column in range(16):
        noisy.putpixel((column, 15), (0, 255, 0, 255))

    canonical_clean = merge_tilesets.canonicalize_tile_for_matching(clean)
    canonical_noisy = merge_tilesets.canonicalize_tile_for_matching(noisy)

    assert canonical_clean.tobytes() == canonical_noisy.tobytes()


def test_compute_category_name_marks_warm_object_tiles_as_furniture() -> None:
    tile = Image.new("RGBA", (16, 16), (0, 0, 0, 255))
    for row in range(4, 12):
        for column in range(4, 12):
            tile.putpixel((column, row), (160, 110, 40, 255))

    assert merge_tilesets.compute_category_name(tile) == "furniture_object"


def test_order_indices_by_local_similarity_keeps_gradual_neighbors_adjacent() -> None:
    dark = Image.new("RGBA", (16, 16), (20, 20, 20, 255))
    mid = Image.new("RGBA", (16, 16), (40, 40, 40, 255))
    bright = Image.new("RGBA", (16, 16), (220, 220, 220, 255))
    representatives = [
        merge_tilesets.TileRecord(Path("bright.png"), 0, 0, bright),
        merge_tilesets.TileRecord(Path("dark.png"), 0, 1, dark),
        merge_tilesets.TileRecord(Path("mid.png"), 0, 2, mid),
    ]

    ordered = merge_tilesets.order_indices_by_local_similarity(representatives, [0, 1, 2])

    assert ordered == [1, 2, 0]
