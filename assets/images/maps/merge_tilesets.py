from __future__ import annotations

import argparse
import csv
import hashlib
from dataclasses import dataclass
from math import ceil
from pathlib import Path

import numpy as np
from PIL import Image

TILESET_COLUMNS = 16
TILESET_ROWS = 8
DEFAULT_TILE_SIZE = 16
DEFAULT_SOURCE_DIR = Path(__file__).resolve().parent / "TILESET"
DEFAULT_EXCLUDED_NAME = "TILESET - FloatingContinent.png"
DEFAULT_OUTPUT_PATH = DEFAULT_SOURCE_DIR / "TILESET - CombinedUnique16px.png"
DEFAULT_REPRESENTATIVE_MANIFEST_PATH = DEFAULT_SOURCE_DIR / "TILESET - CombinedUnique16px.csv"
DEFAULT_MAPPING_PATH = DEFAULT_SOURCE_DIR / "TILESET - CombinedUnique16px.mapping.csv"
DEFAULT_PIXEL_DIFF_THRESHOLD = 1.0
HASH_SAMPLE_SIZE = 8
LAYOUT_SAMPLE_SIZE = 4
LOCAL_SIMILARITY_WINDOW = 48
NOISE_PASSES = 1
SOLID_TILE_TOLERANCE = 12
PROTECTED_CATEGORIES = {
    "furniture_object",
    "object_dark_bg",
    "interior_warm",
    "bright_special",
}


@dataclass(frozen=True)
class TileRecord:
    source_path: Path
    source_row: int
    source_column: int
    tile: Image.Image


@dataclass(frozen=True)
class TileMapping:
    tile_id: int
    match_type: str
    record: TileRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge tiles from tileset PNGs into one deduplicated tileset after "
            "normalizing each tile to a fixed pixel size."
        )
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--exclude", default=DEFAULT_EXCLUDED_NAME)
    parser.add_argument("--tile-size", type=int, default=DEFAULT_TILE_SIZE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_REPRESENTATIVE_MANIFEST_PATH)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--pixel-diff-threshold", type=float, default=DEFAULT_PIXEL_DIFF_THRESHOLD)
    return parser.parse_args()


def infer_source_tile_size(image: Image.Image) -> int:
    width, height = image.size
    if width % TILESET_COLUMNS != 0 or height % TILESET_ROWS != 0:
        raise ValueError(
            "Tileset dimensions are not divisible by the expected grid "
            f"({TILESET_COLUMNS}x{TILESET_ROWS}): {width}x{height}"
        )
    tile_width = width // TILESET_COLUMNS
    tile_height = height // TILESET_ROWS
    if tile_width != tile_height:
        raise ValueError(f"Tileset tiles are not square: {tile_width}x{tile_height}")
    return tile_width


def normalize_tile(tile: Image.Image, tile_size: int) -> Image.Image:
    normalized = tile.convert("RGBA")
    if normalized.size == (tile_size, tile_size):
        return normalized
    return normalized.resize((tile_size, tile_size), Image.Resampling.NEAREST)


def compute_bucket_key(tile: Image.Image) -> tuple[tuple[int, ...], tuple[int, ...]]:
    tile_rgba = np.array(tile, dtype=np.uint8)
    grayscale = np.array(
        tile.convert("L").resize((HASH_SAMPLE_SIZE, HASH_SAMPLE_SIZE), Image.Resampling.BILINEAR),
        dtype=np.uint8,
    )
    average_hash = tuple((grayscale > grayscale.mean()).astype(np.uint8).flatten().tolist())
    alpha_mask = tuple((tile_rgba[:, :, 3] > 0).astype(np.uint8).flatten().tolist())
    return average_hash, alpha_mask


def mean_pixel_difference(left: Image.Image, right: Image.Image) -> float:
    left_rgba = np.array(left, dtype=np.int16)
    right_rgba = np.array(right, dtype=np.int16)
    return float(np.abs(left_rgba - right_rgba).mean())


def rgba_tuple(pixel: np.ndarray) -> tuple[int, int, int, int]:
    return tuple(int(channel) for channel in pixel.tolist())


def smooth_isolated_pixels(tile: Image.Image, passes: int = NOISE_PASSES) -> Image.Image:
    working = np.array(tile, dtype=np.uint8)
    height, width = working.shape[:2]
    for _ in range(passes):
        updated = working.copy()
        for row in range(height):
            for column in range(width):
                neighbors: dict[tuple[int, int, int, int], int] = {}
                for delta_row in (-1, 0, 1):
                    for delta_column in (-1, 0, 1):
                        if delta_row == 0 and delta_column == 0:
                            continue
                        neighbor_row = row + delta_row
                        neighbor_column = column + delta_column
                        if neighbor_row < 0 or neighbor_row >= height or neighbor_column < 0 or neighbor_column >= width:
                            continue
                        key = rgba_tuple(working[neighbor_row, neighbor_column])
                        neighbors[key] = neighbors.get(key, 0) + 1
                if not neighbors:
                    continue
                dominant_pixel, dominant_count = max(neighbors.items(), key=lambda item: item[1])
                center_pixel = rgba_tuple(working[row, column])
                if dominant_pixel != center_pixel and dominant_count >= 5:
                    updated[row, column] = np.array(dominant_pixel, dtype=np.uint8)
        working = updated
    return Image.fromarray(working, mode="RGBA")


def collapse_near_solid_tile(tile: Image.Image, tolerance: int = SOLID_TILE_TOLERANCE) -> Image.Image:
    rgba = np.array(tile, dtype=np.uint8)
    pixels = rgba.reshape(-1, 4)
    counts: dict[tuple[int, int, int, int], int] = {}
    for pixel in pixels:
        key = rgba_tuple(pixel)
        counts[key] = counts.get(key, 0) + 1
    dominant_pixel, dominant_count = max(counts.items(), key=lambda item: item[1])
    if dominant_count >= pixels.shape[0] - tolerance:
        filled = np.empty_like(rgba)
        filled[:, :] = np.array(dominant_pixel, dtype=np.uint8)
        return Image.fromarray(filled, mode="RGBA")
    return tile


def normalize_tile_edges(tile: Image.Image) -> Image.Image:
    edge_fixed = np.array(tile, dtype=np.uint8)
    if edge_fixed.shape[0] < 2 or edge_fixed.shape[1] < 2:
        return tile
    # Ignore 1px extraction noise on the outer border by copying the nearest
    # interior pixels before deduplication.
    edge_fixed[0, :] = edge_fixed[1, :]
    edge_fixed[-1, :] = edge_fixed[-2, :]
    edge_fixed[:, 0] = edge_fixed[:, 1]
    edge_fixed[:, -1] = edge_fixed[:, -2]
    return Image.fromarray(edge_fixed, mode="RGBA")


def canonicalize_tile_for_matching(tile: Image.Image, preserve_structure: bool = False) -> Image.Image:
    edge_normalized = normalize_tile_edges(tile)
    smoothed = smooth_isolated_pixels(edge_normalized)
    if preserve_structure:
        return smoothed
    collapsed = collapse_near_solid_tile(smoothed)
    return collapsed


def quantize_array(values: np.ndarray, levels: int = 16) -> tuple[int, ...]:
    clipped = np.clip(values, 0.0, 255.0)
    quantized = np.rint(clipped * (levels - 1) / 255.0).astype(np.uint8)
    return tuple(int(value) for value in quantized.flatten().tolist())


def compute_layout_vector(tile: Image.Image) -> np.ndarray:
    rgba = np.array(tile, dtype=np.uint8)
    alpha_small = np.array(
        tile.getchannel("A").resize((LAYOUT_SAMPLE_SIZE, LAYOUT_SAMPLE_SIZE), Image.Resampling.NEAREST),
        dtype=np.float32,
    )
    gray = np.array(
        tile.convert("L").resize((LAYOUT_SAMPLE_SIZE, LAYOUT_SAMPLE_SIZE), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    edge_x = np.pad(np.abs(np.diff(gray, axis=1)), ((0, 0), (0, 1)))
    edge_y = np.pad(np.abs(np.diff(gray, axis=0)), ((0, 1), (0, 0)))
    edge = np.clip(edge_x + edge_y, 0, 255)
    rgb_mean = rgba[:, :, :3].mean(axis=(0, 1), dtype=np.float32)
    alpha_coverage = np.array([(rgba[:, :, 3] > 0).mean() * 255.0], dtype=np.float32)
    return np.concatenate(
        [
            alpha_coverage,
            (alpha_small.flatten() > 0).astype(np.float32) * 255.0,
            edge.flatten(),
            gray.flatten(),
            rgb_mean.astype(np.float32),
        ]
    )


def compute_layout_key(tile: Image.Image) -> tuple[int, ...]:
    layout_vector = compute_layout_vector(tile)
    return (
        int(layout_vector[0]),
        *quantize_array(layout_vector[1:17].reshape(4, 4), levels=2),
        *quantize_array(layout_vector[17:33].reshape(4, 4)),
        *quantize_array(layout_vector[33:49].reshape(4, 4)),
        *quantize_array(layout_vector[49:].reshape(1, 3)),
    )


def compute_category_name(tile: Image.Image) -> str:
    rgba = np.array(tile, dtype=np.uint8)
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3]
    gray = rgb.mean(axis=2)
    opaque_mask = alpha > 0
    opaque_ratio = float(opaque_mask.mean())
    if opaque_ratio < 0.1:
        return "empty"

    mean_rgb = rgb.mean(axis=(0, 1))
    dark_ratio = float((gray < 32).mean())
    blue_ratio = float(((rgb[:, :, 2] > rgb[:, :, 1] + 20) & (rgb[:, :, 2] > rgb[:, :, 0] + 20)).mean())
    green_ratio = float(((rgb[:, :, 1] > rgb[:, :, 0] + 15) & (rgb[:, :, 1] > rgb[:, :, 2] + 15)).mean())
    warm_ratio = float(((rgb[:, :, 0] > rgb[:, :, 2] + 18) & (rgb[:, :, 1] > rgb[:, :, 2] - 8)).mean())
    bright_ratio = float((gray > 180).mean())
    color_spread = float(np.abs(rgb - mean_rgb).mean())
    central_crop = rgb[3:13, 3:13]
    central_gray = central_crop.mean(axis=2)
    central_non_dark_ratio = float((central_gray > 48).mean())

    if dark_ratio > 0.95:
        return "black"
    if blue_ratio > 0.28:
        return "water_blue"
    if green_ratio > 0.28:
        return "nature_green"
    if dark_ratio > 0.45 and central_non_dark_ratio > 0.15 and warm_ratio > 0.08:
        return "furniture_object"
    if dark_ratio > 0.45 and central_non_dark_ratio > 0.15:
        return "object_dark_bg"
    if warm_ratio > 0.32 and bright_ratio < 0.25:
        return "interior_warm"
    if color_spread < 12:
        return "flat_surface"
    if bright_ratio > 0.25:
        return "bright_special"
    return "stone_misc"


def category_rank(category_name: str) -> int:
    order = {
        "empty": 0,
        "black": 1,
        "furniture_object": 2,
        "object_dark_bg": 3,
        "interior_warm": 4,
        "stone_misc": 5,
        "water_blue": 6,
        "nature_green": 7,
        "bright_special": 8,
        "flat_surface": 9,
    }
    return order.get(category_name, 99)


def order_indices_by_local_similarity(representatives: list[TileRecord], indices: list[int]) -> list[int]:
    if len(indices) <= 2:
        return sorted(indices, key=lambda index: compute_layout_key(representatives[index].tile))

    sorted_indices = sorted(indices, key=lambda index: compute_layout_key(representatives[index].tile))
    vectors = {index: compute_layout_vector(representatives[index].tile) for index in sorted_indices}
    ordered = [sorted_indices[0]]
    remaining = sorted_indices[1:]

    while remaining:
        current = ordered[-1]
        candidate_pool = remaining[:LOCAL_SIMILARITY_WINDOW]
        next_index = min(
            candidate_pool,
            key=lambda index: (
                float(np.abs(vectors[current] - vectors[index]).sum()),
                compute_layout_key(representatives[index].tile),
            ),
        )
        ordered.append(next_index)
        remaining.remove(next_index)

    return ordered


def iter_tileset_tiles(source_path: Path, tile_size: int) -> list[TileRecord]:
    with Image.open(source_path) as image:
        source_tile_size = infer_source_tile_size(image)
        records: list[TileRecord] = []
        # Large 3x3 objects are still split tile-by-tile here so every piece
        # stays aligned to the common 16x16 grid after normalization.
        for row in range(TILESET_ROWS):
            for column in range(TILESET_COLUMNS):
                left = column * source_tile_size
                top = row * source_tile_size
                tile = image.crop((left, top, left + source_tile_size, top + source_tile_size))
                records.append(
                    TileRecord(
                        source_path=source_path,
                        source_row=row,
                        source_column=column,
                        tile=normalize_tile(tile, tile_size),
                    )
                )
        return records


def deduplicate_tiles(
    source_dir: Path,
    excluded_name: str,
    tile_size: int,
    pixel_diff_threshold: float,
) -> tuple[list[TileRecord], list[TileMapping]]:
    exact_tiles: dict[str, int] = {}
    fuzzy_buckets: dict[tuple[tuple[int, ...], tuple[int, ...]], list[int]] = {}
    canonical_tiles: list[Image.Image] = []
    representatives: list[TileRecord] = []
    mappings: list[TileMapping] = []

    for source_path in sorted(source_dir.glob("TILESET - *.png")):
        if source_path.name == excluded_name or "CombinedUnique16px" in source_path.name:
            continue
        for record in iter_tileset_tiles(source_path, tile_size):
            category_name = compute_category_name(record.tile)
            preserve_structure = category_name in PROTECTED_CATEGORIES
            canonical_tile = canonicalize_tile_for_matching(record.tile, preserve_structure=preserve_structure)
            tile_bytes = canonical_tile.tobytes()
            exact_digest = hashlib.sha256(tile_bytes).hexdigest()
            if exact_digest in exact_tiles:
                mappings.append(TileMapping(tile_id=exact_tiles[exact_digest], match_type="exact", record=record))
                continue

            matched_tile_id: int | None = None
            if pixel_diff_threshold > 0 and not preserve_structure:
                bucket_key = compute_bucket_key(canonical_tile)
                for candidate_tile_id in fuzzy_buckets.get(bucket_key, []):
                    candidate_tile = canonical_tiles[candidate_tile_id]
                    if mean_pixel_difference(canonical_tile, candidate_tile) <= pixel_diff_threshold:
                        matched_tile_id = candidate_tile_id
                        break

            if matched_tile_id is not None:
                mappings.append(TileMapping(tile_id=matched_tile_id, match_type="fuzzy", record=record))
                exact_tiles[exact_digest] = matched_tile_id
                continue

            tile_id = len(representatives)
            representatives.append(record)
            canonical_tiles.append(canonical_tile)
            mappings.append(TileMapping(tile_id=tile_id, match_type="representative", record=record))
            exact_tiles[exact_digest] = tile_id
            bucket_key = compute_bucket_key(canonical_tile)
            fuzzy_buckets.setdefault(bucket_key, []).append(tile_id)

    return representatives, mappings


def reorder_tiles_by_similarity(
    representatives: list[TileRecord],
    mappings: list[TileMapping],
) -> tuple[list[TileRecord], list[TileMapping]]:
    category_buckets: dict[str, list[int]] = {}
    for index, record in enumerate(representatives):
        category_buckets.setdefault(compute_category_name(record.tile), []).append(index)

    ordered_indices: list[int] = []
    for category_name in sorted(category_buckets, key=category_rank):
        ordered_indices.extend(order_indices_by_local_similarity(representatives, category_buckets[category_name]))

    tile_id_map = {old_tile_id: new_tile_id for new_tile_id, old_tile_id in enumerate(ordered_indices)}
    reordered_representatives = [representatives[old_tile_id] for old_tile_id in ordered_indices]
    reordered_mappings = [
        TileMapping(tile_id=tile_id_map[mapping.tile_id], match_type=mapping.match_type, record=mapping.record)
        for mapping in mappings
    ]
    return reordered_representatives, reordered_mappings


def build_output_image(records: list[TileRecord], tile_size: int) -> Image.Image:
    row_count = max(1, ceil(len(records) / TILESET_COLUMNS))
    output = Image.new("RGBA", (TILESET_COLUMNS * tile_size, row_count * tile_size), (0, 0, 0, 0))
    for index, record in enumerate(records):
        x = (index % TILESET_COLUMNS) * tile_size
        y = (index // TILESET_COLUMNS) * tile_size
        output.paste(record.tile, (x, y))
    return output


def write_representative_manifest(records: list[TileRecord], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "tile_id",
                "atlas_row",
                "atlas_column",
                "category",
                "source_tileset",
                "source_row",
                "source_column",
            ],
        )
        writer.writeheader()
        for index, record in enumerate(records):
            writer.writerow(
                {
                    "tile_id": index,
                    "atlas_row": index // TILESET_COLUMNS,
                    "atlas_column": index % TILESET_COLUMNS,
                    "category": compute_category_name(record.tile),
                    "source_tileset": record.source_path.name,
                    "source_row": record.source_row,
                    "source_column": record.source_column,
                }
            )


def write_mapping_manifest(mappings: list[TileMapping], mapping_path: Path) -> None:
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with mapping_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_tileset",
                "source_row",
                "source_column",
                "tile_id",
                "match_type",
            ],
        )
        writer.writeheader()
        for mapping in mappings:
            writer.writerow(
                {
                    "source_tileset": mapping.record.source_path.name,
                    "source_row": mapping.record.source_row,
                    "source_column": mapping.record.source_column,
                    "tile_id": mapping.tile_id,
                    "match_type": mapping.match_type,
                }
            )


def main() -> None:
    args = parse_args()
    representatives, mappings = deduplicate_tiles(
        source_dir=args.source_dir,
        excluded_name=args.exclude,
        tile_size=args.tile_size,
        pixel_diff_threshold=args.pixel_diff_threshold,
    )
    representatives, mappings = reorder_tiles_by_similarity(representatives, mappings)
    output_image = build_output_image(representatives, tile_size=args.tile_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_image.save(args.output)
    write_representative_manifest(representatives, args.manifest)
    write_mapping_manifest(mappings, args.mapping)
    fuzzy_matches = sum(1 for mapping in mappings if mapping.match_type == "fuzzy")
    exact_matches = sum(1 for mapping in mappings if mapping.match_type == "exact")
    print(f"source_dir={args.source_dir}")
    print(f"excluded={args.exclude}")
    print(f"pixel_diff_threshold={args.pixel_diff_threshold}")
    print(f"unique_tiles={len(representatives)}")
    print(f"exact_matches={exact_matches}")
    print(f"fuzzy_matches={fuzzy_matches}")
    print(f"output={args.output}")
    print(f"manifest={args.manifest}")
    print(f"mapping={args.mapping}")


if __name__ == "__main__":
    main()
