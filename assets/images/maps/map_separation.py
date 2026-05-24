from __future__ import annotations

import argparse
import colorsys
import csv
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import numpy as np
from PIL import Image

INNER_MARGIN = 1
COMPARISON_TILE_SIZE = 16
EDGE_IGNORE_MARGIN = 1
SUSPICIOUS_SCORE_THRESHOLD = 500
INNER_SCORE_WEIGHT = 0.3
CENTER_SCORE_WEIGHT = 6.0
LOWER_BLOCK_SCORE_WEIGHT = 4.0
BLOCK_SCORE_WEIGHT = 5.0
EDGE_SCORE_WEIGHT = 0.5
PROFILE_SCORE_WEIGHT = 1.0
FULL_SCORE_WEIGHT = 0.05
NEIGHBOR_SCORE_WEIGHT = 0.1
COLOR_SCORE_WEIGHT = 45.0
DEFAULT_MAP_OFFSET_X = 0
DEFAULT_MAP_OFFSET_Y = 0
DEFAULT_MAP_TILE_COLUMNS = None
DEFAULT_MAP_TILE_ROWS = None
DEFAULT_SCREENSHOT_TILESET_TILE_SIZE = 38
DEFAULT_SCREENSHOT_MAP_TILE_SIZE = 32
TILESET_COLUMNS = 16
TILESET_ROWS = 8
WORKSPACE_TOP_SEARCH_LIMIT = 120
TILESET_SEARCH_HEIGHT = 380
TILESET_SEARCH_WIDTH = 700
TILESET_TAB_SEARCH_HEIGHT = 90
TILESET_TAB_SEARCH_WIDTH = 220
TILESET_TAB_BLUE_THRESHOLD = 0.1
TILESET_TAB_TOP_OFFSET = 2
TILESET_EDGE_RUN = 4
TILESET_EDGE_CHECKER_THRESHOLD = 0.2
TILESET_EDGE_LIGHT_THRESHOLD = 0.05
TILESET_SIZE_SEARCH_MARGIN = 3
EDGE_PERCENTILE = 75.0
MAP_BLACK_THRESHOLD = 10.0
MAP_ROW_CONTENT_THRESHOLD = 8
MAP_COL_CONTENT_THRESHOLD = 4
MAP_FULL_HEIGHT_COLUMN_RATIO = 0.9
MAP_COMPONENT_MIN_AREA = 400
MAP_COMPONENT_MIN_SIDE = 24
MAP_COMPONENT_MIN_THICKNESS = 8
MAP_GREEN_AREA_MIN_RATIO = 0.02
MAP_GREEN_AREA_MIN_PIXELS = 5000
MAP_NEUTRAL_COLUMN_RATIO = 0.95
TILESET_NEUTRAL_ROW_RATIO = 0.98
TILESET_LIGHT_ROW_RATIO = 0.98
MAP_COMPONENT_SCORE_WINDOW = 5000.0
MAP_SCORE_MIN_TILE_COUNT = 4
MAP_SCORE_BRANCH_MIN_AREA_RATIO = 0.15
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TILESET_PATH = BASE_DIR / "TILESET" / "TILESET - SealedCave.png"
DEFAULT_MAP_PATH = BASE_DIR / "Sealed_Cave_B2_2.png"


class OutputPaths(TypedDict):
    comparison: Path
    csv: Path


class DebugCell(TypedDict):
    tile_id: int
    mode: str
    score: int


class AnalyzeSummary(TypedDict):
    result: list[list[int]]
    debug_rows: list[list[DebugCell]]
    tile_size: int
    tileset_tile_size: int
    output_paths: OutputPaths


@dataclass(frozen=True)
class TileFeatures:
    tile: np.ndarray
    inner_tile_i32: np.ndarray
    inner_edge_view: np.ndarray
    col_signature: np.ndarray
    row_signature: np.ndarray
    block_signature: np.ndarray
    center_block_signature: np.ndarray
    lower_block_signature: np.ndarray
    color_signature: np.ndarray
    full_tile_i32: np.ndarray
    left_edge_i32: np.ndarray
    top_edge_i32: np.ndarray


@dataclass(frozen=True)
class ChunkFeatures:
    chunk: np.ndarray
    inner_chunk_i32: np.ndarray
    inner_edge_view: np.ndarray
    col_signature: np.ndarray
    row_signature: np.ndarray
    block_signature: np.ndarray
    center_block_signature: np.ndarray
    lower_block_signature: np.ndarray
    color_signature: np.ndarray
    full_chunk_i32: np.ndarray
    left_neighbor_edge_i32: np.ndarray | None
    top_neighbor_edge_i32: np.ndarray | None


@dataclass(frozen=True)
class BoundingBox:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def crop(self, image: Image.Image) -> Image.Image:
        return image.crop((self.left, self.top, self.right, self.bottom))


def open_image(path: Path) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")
    return Image.open(path).convert("RGBA")


def rgb_view(image_np: np.ndarray) -> np.ndarray:
    return image_np[:, :, :3]


def is_light_pixel(rgb: np.ndarray) -> np.ndarray:
    return np.asarray((rgb >= 232).all(axis=-1))


def is_pale_ui_pixel(rgb: np.ndarray) -> np.ndarray:
    return np.asarray((rgb >= 220).all(axis=-1))


def is_checker_pixel(rgb: np.ndarray) -> np.ndarray:
    spread = rgb.max(axis=-1) - rgb.min(axis=-1)
    mean = rgb.mean(axis=-1)
    return np.asarray((spread <= 10) & (mean >= 38) & (mean <= 96))


def is_green_canvas_pixel(rgb: np.ndarray) -> np.ndarray:
    red = rgb[..., 0].astype(np.int16)
    green = rgb[..., 1].astype(np.int16)
    blue = rgb[..., 2].astype(np.int16)
    return np.asarray((green >= 70) & (green - red >= 35) & (green - blue >= 35))


def detect_workspace_top(image_np: np.ndarray) -> int:
    height, width = image_np.shape[:2]
    rgb = rgb_view(image_np)
    x0 = width // 3
    x1 = min(width, x0 + width // 4)
    search_limit = min(WORKSPACE_TOP_SEARCH_LIMIT, height)

    for y in range(search_limit):
        row = rgb[y, x0:x1]
        if row.size == 0:
            continue
        checker_ratio = float(is_checker_pixel(row).mean())
        light_ratio = float(is_light_pixel(row).mean())
        if checker_ratio >= 0.45 and light_ratio <= 0.35:
            return y

    raise ValueError("Could not detect the workspace top boundary in the screenshot.")


def largest_component_bbox(mask: np.ndarray) -> BoundingBox:
    components = component_bboxes(mask)
    if not components:
        raise ValueError("Could not find a connected component in the detection mask.")
    return max(components, key=lambda item: item[0])[1]


def component_bboxes(mask: np.ndarray) -> list[tuple[int, BoundingBox]]:
    if mask.ndim != 2:
        raise ValueError("Component mask must be 2-dimensional.")

    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[tuple[int, BoundingBox]] = []

    for start_y in range(height):
        for start_x in range(width):
            if not mask[start_y, start_x] or visited[start_y, start_x]:
                continue

            queue = deque([(start_y, start_x)])
            visited[start_y, start_x] = True
            min_x = max_x = start_x
            min_y = max_y = start_y
            area = 0

            while queue:
                y, x = queue.popleft()
                area += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

                for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if not (0 <= next_y < height and 0 <= next_x < width):
                        continue
                    if visited[next_y, next_x] or not mask[next_y, next_x]:
                        continue
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))

            components.append((area, BoundingBox(min_x, min_y, max_x + 1, max_y + 1)))

    return components


def find_map_canvas_bbox(image_np: np.ndarray, workspace_top: int) -> BoundingBox:
    rgb = rgb_view(image_np)
    search_region = rgb[workspace_top:, : image_np.shape[1] * 2 // 3]
    mean = search_region.mean(axis=-1)
    spread = search_region.max(axis=-1) - search_region.min(axis=-1)
    checker_mask = (spread <= 8) & (mean >= 38) & (mean <= 62)
    light_mask = (search_region >= 232).all(axis=-1)
    black_mask = mean <= MAP_BLACK_THRESHOLD
    content_mask = ~(checker_mask | light_mask | black_mask)
    green_mask = is_green_canvas_pixel(search_region)
    component_bbox: BoundingBox | None = None
    if green_mask.any():
        green_components = component_bboxes(green_mask)
        min_green_area = max(
            MAP_GREEN_AREA_MIN_PIXELS,
            (search_region.shape[0] * search_region.shape[1]) * MAP_GREEN_AREA_MIN_RATIO,
        )
        large_green_components = [
            (area, bbox)
            for area, bbox in green_components
            if area >= MAP_COMPONENT_MIN_AREA
            and max(bbox.width, bbox.height) >= MAP_COMPONENT_MIN_SIDE
            and min(bbox.width, bbox.height) >= MAP_COMPONENT_MIN_THICKNESS
        ]
        total_green_area = sum(area for area, _ in large_green_components)
        if total_green_area >= min_green_area:
            component_bbox = BoundingBox(
                left=min(bbox.left for _, bbox in large_green_components),
                top=min(bbox.top for _, bbox in large_green_components),
                right=max(bbox.right for _, bbox in large_green_components),
                bottom=max(bbox.bottom for _, bbox in large_green_components),
            )
        else:
            green_mask = None
    else:
        green_mask = None

    if green_mask is None:
        components = component_bboxes(content_mask)
        large_components = [
            bbox
            for area, bbox in components
            if area >= MAP_COMPONENT_MIN_AREA
            and max(bbox.width, bbox.height) >= MAP_COMPONENT_MIN_SIDE
            and min(bbox.width, bbox.height) >= MAP_COMPONENT_MIN_THICKNESS
        ]
        if not large_components:
            component_bbox = largest_component_bbox(content_mask)
        else:
            component_bbox = BoundingBox(
                left=min(bbox.left for bbox in large_components),
                top=min(bbox.top for bbox in large_components),
                right=max(bbox.right for bbox in large_components),
                bottom=max(bbox.bottom for bbox in large_components),
            )
    if component_bbox is None:
        raise ValueError("Could not determine the map canvas bounds in the screenshot.")
    return BoundingBox(
        component_bbox.left,
        component_bbox.top + workspace_top,
        component_bbox.right,
        component_bbox.bottom + workspace_top,
    )


def snap_length_to_tile(length: int, tile_size: int) -> int:
    if tile_size <= 0:
        return length
    return ((length + tile_size - 1) // tile_size) * tile_size


def floor_length_to_tile(length: int, tile_size: int) -> int:
    if tile_size <= 0:
        return length
    return (length // tile_size) * tile_size


def trim_map_component_bbox(
    map_region: np.ndarray,
    content_mask: np.ndarray,
    component_bbox: BoundingBox,
    tile_size: int,
) -> BoundingBox | None:
    mean = map_region.mean(axis=-1)
    visual_mask = ~( (mean <= MAP_BLACK_THRESHOLD) | is_checker_pixel(map_region) )
    row_counts = content_mask.sum(axis=1)
    col_counts = content_mask.sum(axis=0)
    full_height_threshold = max(1, int(content_mask.shape[0] * MAP_FULL_HEIGHT_COLUMN_RATIO))
    row_threshold = max(MAP_ROW_CONTENT_THRESHOLD, tile_size // 2)
    col_threshold = max(MAP_COL_CONTENT_THRESHOLD, tile_size // 4)

    row_start = component_bbox.top
    row_end = component_bbox.bottom
    col_start = component_bbox.left
    col_end = component_bbox.right

    left_margin = 0
    for count in col_counts[col_start:col_end]:
        if count >= full_height_threshold:
            left_margin += 1
            continue
        break
    if 0 < left_margin < tile_size:
        neutral_ratio = is_checker_pixel(
            map_region[row_start:row_end, col_start : col_start + left_margin]
        ).mean()
        if neutral_ratio >= MAP_NEUTRAL_COLUMN_RATIO:
            col_start += left_margin

    significant_rows = np.where(row_counts[row_start:row_end] >= row_threshold)[0]
    significant_cols = np.where(col_counts[col_start:col_end] >= col_threshold)[0]
    if len(significant_rows) == 0 or len(significant_cols) == 0:
        return None

    row_start += int(significant_rows[0])
    row_end = row_start + int(significant_rows[-1] - significant_rows[0]) + 1
    col_start += int(significant_cols[0])
    col_end = col_start + int(significant_cols[-1] - significant_cols[0]) + 1

    while True:
        right_search_end = min(map_region.shape[1], col_end + tile_size)
        if right_search_end <= col_end:
            break
        right_strip = visual_mask[row_start:row_end, col_end:right_search_end]
        if right_strip.size == 0:
            break
        right_cols = np.where(right_strip.sum(axis=0) >= col_threshold)[0]
        if len(right_cols) == 0:
            break
        new_col_end = col_end + int(right_cols[-1]) + 1
        if new_col_end <= col_end:
            break
        col_end = new_col_end

    while True:
        bottom_search_end = min(map_region.shape[0], row_end + tile_size)
        if bottom_search_end <= row_end:
            break
        bottom_strip = visual_mask[row_end:bottom_search_end, col_start:col_end]
        if bottom_strip.size == 0:
            break
        bottom_rows = np.where(bottom_strip.sum(axis=1) >= row_threshold)[0]
        if len(bottom_rows) == 0:
            break
        new_row_end = row_end + int(bottom_rows[-1]) + 1
        if new_row_end <= row_end:
            break
        row_end = new_row_end

    raw_width = col_end - col_start
    raw_height = row_end - row_start
    refined_width = floor_length_to_tile(raw_width, tile_size)
    refined_height = floor_length_to_tile(raw_height, tile_size)
    if refined_width < tile_size:
        refined_width = snap_length_to_tile(raw_width, tile_size)
    if refined_height < tile_size:
        refined_height = snap_length_to_tile(raw_height, tile_size)

    discarded_width = raw_width - refined_width
    if (
        tile_size > 0
        and 0 < discarded_width < tile_size
        and refined_width + tile_size <= content_mask.shape[1] - col_start
    ):
        right_strip = col_counts[col_start + refined_width : col_end]
        if len(right_strip) > 0 and right_strip.max(initial=0) >= col_threshold:
            refined_width = snap_length_to_tile(raw_width, tile_size)

    discarded_height = raw_height - refined_height
    if (
        tile_size > 0
        and 0 < discarded_height < tile_size
        and refined_height + tile_size <= content_mask.shape[0] - row_start
    ):
        bottom_strip = row_counts[row_start + refined_height : row_end]
        if len(bottom_strip) > 0 and bottom_strip.max(initial=0) >= row_threshold:
            refined_height = snap_length_to_tile(raw_height, tile_size)

    refined_right = min(content_mask.shape[1], col_start + refined_width)
    refined_bottom = min(content_mask.shape[0], row_start + refined_height)
    if refined_right - col_start < tile_size or refined_bottom - row_start < tile_size:
        return None

    return BoundingBox(
        left=col_start,
        top=row_start,
        right=refined_right,
        bottom=refined_bottom,
    )


def score_map_candidate_bbox(
    map_region: np.ndarray,
    candidate_bbox: BoundingBox,
    tileset_np: np.ndarray,
    tile_size: int,
) -> float:
    usable_width = floor_length_to_tile(candidate_bbox.width, tile_size)
    usable_height = floor_length_to_tile(candidate_bbox.height, tile_size)
    if usable_width < tile_size or usable_height < tile_size:
        return float("-inf")
    tile_count = (usable_width // tile_size) * (usable_height // tile_size)
    if tile_count < MAP_SCORE_MIN_TILE_COUNT:
        return float("-inf")

    candidate_map = map_region[
        candidate_bbox.top : candidate_bbox.top + usable_height,
        candidate_bbox.left : candidate_bbox.left + usable_width,
    ]
    return score_tileset_against_map(candidate_map, tileset_np, tile_size)


def trim_neutral_columns(
    map_region: np.ndarray,
    candidate_bbox: BoundingBox,
    tile_size: int,
) -> BoundingBox:
    candidate = map_region[candidate_bbox.top : candidate_bbox.bottom, candidate_bbox.left : candidate_bbox.right]
    neutral_ratio = is_checker_pixel(candidate).mean(axis=0)
    left_trim = 0
    for ratio in neutral_ratio:
        if ratio < MAP_NEUTRAL_COLUMN_RATIO:
            break
        left_trim += 1

    if 0 < left_trim < candidate_bbox.width:
        shifted_right = min(map_region.shape[1], candidate_bbox.right + left_trim)
        shifted_width = shifted_right - (candidate_bbox.left + left_trim)
        if shifted_width >= tile_size:
            return BoundingBox(
                left=candidate_bbox.left + left_trim,
                top=candidate_bbox.top,
                right=shifted_right,
                bottom=candidate_bbox.bottom,
            )

        remaining_width = candidate_bbox.width - left_trim
        snapped_trim = min(left_trim, max(0, remaining_width - tile_size))
        return BoundingBox(
            left=candidate_bbox.left + snapped_trim,
            top=candidate_bbox.top,
            right=candidate_bbox.right,
            bottom=candidate_bbox.bottom,
        )

    return candidate_bbox


def bbox_omits_significant_content(
    content_mask: np.ndarray,
    outer_bbox: BoundingBox,
    inner_bbox: BoundingBox,
    row_threshold: int,
    col_threshold: int,
) -> bool:
    if inner_bbox.left > outer_bbox.left:
        left_strip = content_mask[outer_bbox.top : outer_bbox.bottom, outer_bbox.left : inner_bbox.left]
        if left_strip.size > 0 and left_strip.sum(axis=0).max() >= row_threshold:
            return True
    if inner_bbox.right < outer_bbox.right:
        right_strip = content_mask[outer_bbox.top : outer_bbox.bottom, inner_bbox.right : outer_bbox.right]
        if right_strip.size > 0 and right_strip.sum(axis=0).max() >= row_threshold:
            return True
    if inner_bbox.top > outer_bbox.top:
        top_strip = content_mask[outer_bbox.top : inner_bbox.top, outer_bbox.left : outer_bbox.right]
        if top_strip.size > 0 and top_strip.sum(axis=1).max() >= col_threshold:
            return True
    if inner_bbox.bottom < outer_bbox.bottom:
        bottom_strip = content_mask[inner_bbox.bottom : outer_bbox.bottom, outer_bbox.left : outer_bbox.right]
        if bottom_strip.size > 0 and bottom_strip.sum(axis=1).max() >= col_threshold:
            return True
    return False


def refine_map_canvas_bbox(
    image_np: np.ndarray,
    map_bbox: BoundingBox,
    tile_size: int,
    tileset_np: np.ndarray | None = None,
) -> BoundingBox:
    map_region = rgb_view(image_np[map_bbox.top : map_bbox.bottom, map_bbox.left : map_bbox.right])
    mean = map_region.mean(axis=-1)
    black_mask = mean <= MAP_BLACK_THRESHOLD
    checker_mask = is_checker_pixel(map_region)
    light_mask = (map_region >= 232).all(axis=-1)
    content_mask = ~(black_mask | checker_mask | light_mask)
    components = component_bboxes(content_mask)
    large_components = [
        bbox
        for area, bbox in components
        if area >= MAP_COMPONENT_MIN_AREA
        and max(bbox.width, bbox.height) >= MAP_COMPONENT_MIN_SIDE
        and min(bbox.width, bbox.height) >= MAP_COMPONENT_MIN_THICKNESS
    ]
    if not large_components:
        return map_bbox

    component_bbox = BoundingBox(
        left=min(bbox.left for bbox in large_components),
        top=min(bbox.top for bbox in large_components),
        right=max(bbox.right for bbox in large_components),
        bottom=max(bbox.bottom for bbox in large_components),
    )
    row_threshold = max(MAP_ROW_CONTENT_THRESHOLD, tile_size // 2)
    col_threshold = max(MAP_COL_CONTENT_THRESHOLD, tile_size // 4)
    trimmed_union_bbox = trim_map_component_bbox(map_region, content_mask, component_bbox, tile_size)
    if trimmed_union_bbox is not None:
        trimmed_union_bbox = trim_neutral_columns(map_region, trimmed_union_bbox, tile_size)

    if tileset_np is not None:
        scored_candidates: list[tuple[float, int, BoundingBox]] = []
        for candidate_bbox in large_components:
            trimmed_bbox = trim_map_component_bbox(map_region, content_mask, candidate_bbox, tile_size)
            if trimmed_bbox is None:
                continue
            trimmed_bbox = trim_neutral_columns(map_region, trimmed_bbox, tile_size)
            score = score_map_candidate_bbox(map_region, trimmed_bbox, tileset_np, tile_size)
            scored_candidates.append((score, trimmed_bbox.width * trimmed_bbox.height, trimmed_bbox))

        if scored_candidates:
            best_score = max(score for score, _, _ in scored_candidates)
            merged_candidates = [
                bbox
                for score, _, bbox in scored_candidates
                if score >= best_score - MAP_COMPONENT_SCORE_WINDOW
            ]
            best_bbox = BoundingBox(
                left=min(bbox.left for bbox in merged_candidates),
                top=min(bbox.top for bbox in merged_candidates),
                right=max(bbox.right for bbox in merged_candidates),
                bottom=max(bbox.bottom for bbox in merged_candidates),
            )
            union_area = max(1, component_bbox.width * component_bbox.height)
            selected_area_ratio = (best_bbox.width * best_bbox.height) / union_area
            if (
                selected_area_ratio >= MAP_SCORE_BRANCH_MIN_AREA_RATIO
                and (
                    trimmed_union_bbox is None
                    or not bbox_omits_significant_content(
                        content_mask,
                        trimmed_union_bbox,
                        best_bbox,
                        row_threshold,
                        col_threshold,
                    )
                )
            ):
                return BoundingBox(
                    left=map_bbox.left + best_bbox.left,
                    top=map_bbox.top + best_bbox.top,
                    right=map_bbox.left + best_bbox.right,
                    bottom=map_bbox.top + best_bbox.bottom,
                )
    if trimmed_union_bbox is None:
        return map_bbox

    return BoundingBox(
        left=map_bbox.left + trimmed_union_bbox.left,
        top=map_bbox.top + trimmed_union_bbox.top,
        right=map_bbox.left + trimmed_union_bbox.right,
        bottom=map_bbox.top + trimmed_union_bbox.bottom,
    )


def longest_true_run(mask: np.ndarray) -> tuple[int, int]:
    best_start = best_end = 0
    current_start = None

    for index, value in enumerate(mask):
        if value and current_start is None:
            current_start = index
        if not value and current_start is not None:
            if index - current_start > best_end - best_start:
                best_start, best_end = current_start, index
            current_start = None

    if current_start is not None and len(mask) - current_start > best_end - best_start:
        best_start, best_end = current_start, len(mask)

    return best_start, best_end


def find_first_run(mask: np.ndarray, min_run: int) -> int | None:
    run = 0
    for index, value in enumerate(mask):
        run = run + 1 if value else 0
        if run >= min_run:
            return index - run + 1
    return None


def find_last_run(mask: np.ndarray, min_run: int) -> int | None:
    run = 0
    for index in range(len(mask) - 1, -1, -1):
        if mask[index]:
            run += 1
            if run >= min_run:
                return index + run - 1
        else:
            run = 0
    return None


def normalized_autocorrelation(signal: np.ndarray, lag: int) -> float:
    if lag <= 0 or lag >= len(signal):
        return -1.0
    lhs = signal[:-lag].astype(np.float64)
    rhs = signal[lag:].astype(np.float64)
    lhs -= lhs.mean()
    rhs -= rhs.mean()
    denominator = np.linalg.norm(lhs) * np.linalg.norm(rhs)
    if denominator == 0:
        return -1.0
    return float(lhs.dot(rhs) / denominator)


def grayscale_view(image: np.ndarray) -> np.ndarray:
    return image.astype(np.float32).mean(axis=2)


def edge_projection_signals(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gray = grayscale_view(image)
    horizontal_edges = np.abs(np.diff(gray, axis=1))
    vertical_edges = np.abs(np.diff(gray, axis=0))

    horizontal_threshold = np.percentile(horizontal_edges, EDGE_PERCENTILE)
    vertical_threshold = np.percentile(vertical_edges, EDGE_PERCENTILE)
    horizontal_mask = horizontal_edges >= horizontal_threshold
    vertical_mask = vertical_edges >= vertical_threshold

    col_signal = horizontal_edges.mean(axis=0) + (horizontal_mask.mean(axis=0) * 255.0)
    row_signal = vertical_edges.mean(axis=1) + (vertical_mask.mean(axis=1) * 255.0)
    return col_signal, row_signal


def periodicity_score(col_signal: np.ndarray, row_signal: np.ndarray, tile_size: int) -> float:
    return (
        normalized_autocorrelation(col_signal, tile_size)
        + 0.25 * normalized_autocorrelation(row_signal, tile_size)
    )


def rank_tile_sizes_from_region(
    region: np.ndarray,
    min_tile_size: int = 8,
    max_tile_size: int | None = None,
    prefer_larger: bool = True,
) -> list[int]:
    inferred_max_tile_size = min(region.shape[1], region.shape[0])
    if max_tile_size is None:
        max_tile_size = inferred_max_tile_size
    else:
        max_tile_size = min(max_tile_size, inferred_max_tile_size)
    if max_tile_size <= 0:
        raise ValueError("Search region is too small to contain tile patterns.")

    max_candidate = max_tile_size

    gray = grayscale_view(region)
    intensity_col_signal = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    intensity_row_signal = np.abs(np.diff(gray, axis=0)).mean(axis=1)
    edge_col_signal, edge_row_signal = edge_projection_signals(region)

    candidate_scores = []
    for tile_size in range(min_tile_size, max_candidate + 1):
        intensity_score = periodicity_score(intensity_col_signal, intensity_row_signal, tile_size)
        edge_score = periodicity_score(edge_col_signal, edge_row_signal, tile_size)
        combined_score = intensity_score + edge_score
        candidate_scores.append((combined_score, tile_size))

    if not candidate_scores:
        raise ValueError("Could not derive any tile-size candidates from the tileset preview.")

    best_score = max(score for score, _ in candidate_scores)
    ranked = sorted(
        (
            (score, tile_size)
            for score, tile_size in candidate_scores
            if score >= best_score * 0.92
        ),
        key=lambda item: (-item[0], -item[1] if prefer_larger else item[1]),
    )
    if not ranked:
        ranked = sorted(
            candidate_scores,
            key=lambda item: (-item[0], -item[1] if prefer_larger else item[1]),
        )
    return [tile_size for _, tile_size in ranked[:8]]


def rank_tileset_tile_sizes(search_region: np.ndarray, rough_width: int) -> list[int]:
    max_tile_size = min(search_region.shape[1] // TILESET_COLUMNS, search_region.shape[0] // TILESET_ROWS)
    return rank_tile_sizes_from_region(
        search_region,
        min_tile_size=8,
        max_tile_size=max_tile_size,
        prefer_larger=True,
    )


def detect_tileset_tile_size(search_region: np.ndarray, rough_width: int) -> int:
    return rank_tileset_tile_sizes(search_region, rough_width)[0]


def detect_map_tile_size(map_region: np.ndarray, max_tile_size: int = 64) -> int:
    return rank_tile_sizes_from_region(
        map_region,
        min_tile_size=8,
        max_tile_size=max_tile_size,
        prefer_larger=False,
    )[0]


def detect_tileset_top_boundary(image_np: np.ndarray, workspace_top: int) -> int:
    height, width = image_np.shape[:2]
    panel_left = max(0, width - TILESET_SEARCH_WIDTH)
    tab_right = min(width, panel_left + 120)
    panel_region = rgb_view(image_np[: min(height, TILESET_TAB_SEARCH_HEIGHT), panel_left:tab_right])
    blue_ratio = (
        (panel_region[:, :, 2] > 180) & (panel_region[:, :, 0] < 80) & (panel_region[:, :, 1] < 170)
    ).mean(axis=1)
    blue_rows = np.where(blue_ratio >= TILESET_TAB_BLUE_THRESHOLD)[0]
    if len(blue_rows) == 0:
        return workspace_top
    return max(workspace_top - 8, int(blue_rows[-1]) + 1)


def is_layer1_blue_pixel(rgb: np.ndarray) -> np.ndarray:
    return (rgb[..., 2] > 180) & (rgb[..., 0] < 80) & (rgb[..., 1] < 170)


def detect_layer1_tab_bbox(image_np: np.ndarray, workspace_top: int) -> BoundingBox:
    height, width = image_np.shape[:2]
    panel_left = max(0, width - TILESET_SEARCH_WIDTH)
    panel_top = 0
    panel_right = width
    panel_bottom = min(height, max(workspace_top, 1))
    panel_region = rgb_view(image_np[panel_top:panel_bottom, panel_left:panel_right])
    blue_mask = is_layer1_blue_pixel(panel_region)
    components = component_bboxes(blue_mask)
    if not components:
        raise ValueError("Could not detect the active Layer 1 tab in the screenshot.")

    filtered_components = [
        bbox
        for area, bbox in components
        if area >= 400 and bbox.width >= 24 and bbox.height >= 16
    ]
    if not filtered_components:
        filtered_components = [bbox for _, bbox in components]

    component_bbox = max(
        filtered_components,
        key=lambda bbox: (
            bbox.right,
            -bbox.top,
            bbox.width * bbox.height,
        ),
    )
    return BoundingBox(
        left=panel_left + component_bbox.left,
        top=panel_top + component_bbox.top,
        right=panel_left + component_bbox.right,
        bottom=panel_top + component_bbox.bottom,
    )


def score_tileset_crop(crop: np.ndarray, tile_size: int) -> float:
    gray = grayscale_view(crop)
    intensity_col_signal = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    intensity_row_signal = np.abs(np.diff(gray, axis=0)).mean(axis=1)
    edge_col_signal, edge_row_signal = edge_projection_signals(crop)
    return (
        periodicity_score(intensity_col_signal, intensity_row_signal, tile_size)
        + periodicity_score(edge_col_signal, edge_row_signal, tile_size)
        - float(is_checker_pixel(crop).mean())
        - (2.0 * float(is_light_pixel(crop).mean()))
    )


def score_tileset_against_map(
    map_np: np.ndarray,
    tileset_np: np.ndarray,
    tile_size: int,
    max_samples_per_axis: int = 24,
) -> float:
    tiles = split_tiles(tileset_np, tile_size)
    tile_features = build_tile_features(tiles)
    map_height, map_width = map_np.shape[:2]
    tile_rows = map_height // tile_size
    tile_columns = map_width // tile_size
    if tile_rows <= 0 or tile_columns <= 0:
        return float("-inf")

    sampled_rows = min(tile_rows, max_samples_per_axis)
    sampled_columns = min(tile_columns, max_samples_per_axis)
    row_indices = sorted(set(np.linspace(0, tile_rows - 1, sampled_rows, dtype=int).tolist()))
    col_indices = sorted(set(np.linspace(0, tile_columns - 1, sampled_columns, dtype=int).tolist()))

    total_score = 0
    exact_matches = 0
    sample_count = 0
    for row_index in row_indices:
        y = row_index * tile_size
        for col_index in col_indices:
            x = col_index * tile_size
            chunk = map_np[y : y + tile_size, x : x + tile_size]
            chunk_features = build_chunk_features(chunk)
            _, match_mode, score = find_tile(
                chunk,
                tiles,
                tile_features=tile_features,
                chunk_features=chunk_features,
            )
            total_score += score / max(1, chunk_features.inner_chunk_i32.size)
            exact_matches += int(match_mode == "inner_exact")
            sample_count += 1

    if sample_count == 0:
        return float("-inf")

    average_score = total_score / sample_count
    exact_match_ratio = exact_matches / sample_count
    return -average_score + (exact_match_ratio * 250.0)


def refine_tileset_left(search_region: np.ndarray, rough_left: int, tile_size: int) -> int:
    crop_width = tile_size * TILESET_COLUMNS
    crop_height = tile_size * TILESET_ROWS
    max_left = search_region.shape[1] - crop_width
    if max_left < 0:
        raise ValueError("Search region is narrower than the expected tileset preview width.")

    clamped_left = min(max_left, max(0, rough_left))
    left_start = clamped_left
    left_end = min(max_left, clamped_left + tile_size - 1)

    best_score = None
    best_left = None
    for left in range(left_start, left_end + 1):
        crop = search_region[:crop_height, left : left + crop_width]
        if crop.shape[:2] != (crop_height, crop_width):
            continue
        score = score_tileset_crop(crop, tile_size)
        if best_score is None or score > best_score:
            best_score = score
            best_left = left

    if best_left is None:
        return clamped_left
    return best_left


def build_tileset_candidate_bbox(
    image_np: np.ndarray,
    search_left: int,
    search_top: int,
    search_bottom: int,
    tile_size: int,
) -> BoundingBox:
    search_region = rgb_view(image_np[search_top:search_bottom, search_left:])
    preview_band_height = min(search_region.shape[0], 140)
    preview_band = search_region[:preview_band_height]
    checker_ratio = is_checker_pixel(preview_band).mean(axis=0)
    light_ratio = is_light_pixel(preview_band).mean(axis=0)
    content_mask = (
        (checker_ratio <= TILESET_EDGE_CHECKER_THRESHOLD)
        & (light_ratio <= TILESET_EDGE_LIGHT_THRESHOLD)
    )

    rough_left = find_first_run(content_mask, TILESET_EDGE_RUN)
    rough_right = find_last_run(content_mask, TILESET_EDGE_RUN)
    if rough_left is None or rough_right is None or rough_right <= rough_left:
        raise ValueError("Could not detect the rough tileset preview bounds in the screenshot.")

    crop_width = tile_size * TILESET_COLUMNS
    crop_height = tile_size * TILESET_ROWS
    max_left = search_region.shape[1] - crop_width
    left = min(max_left, refine_tileset_left(search_region, rough_left=rough_left, tile_size=tile_size))
    right = search_left + left + crop_width
    bottom = search_top + crop_height
    left = search_left + left

    if right > image_np.shape[1] or bottom > image_np.shape[0]:
        raise ValueError("The inferred tileset preview extends past the screenshot boundary.")

    return BoundingBox(left, search_top, right, bottom)


def score_tileset_candidate_bbox(
    image_np: np.ndarray,
    candidate_bbox: BoundingBox,
    tile_size: int,
    map_np: np.ndarray | None = None,
) -> float:
    candidate_crop = rgb_view(
        image_np[
            candidate_bbox.top : candidate_bbox.bottom,
            candidate_bbox.left : candidate_bbox.right,
        ]
    )
    candidate_score = score_tileset_crop(candidate_crop, tile_size)
    if map_np is not None:
        candidate_score += score_tileset_against_map(map_np, candidate_crop, tile_size)
    return candidate_score


def refine_anchored_tileset_bbox(
    image_np: np.ndarray,
    anchor_left: int,
    anchor_top: int,
    tile_size: int,
) -> BoundingBox | None:
    height, width = image_np.shape[:2]
    crop_width = tile_size * TILESET_COLUMNS
    crop_height = tile_size * TILESET_ROWS
    if anchor_left < 0 or anchor_left + crop_width > width:
        return None

    best_bbox = None
    best_score = None
    max_shift = min(8, tile_size)
    for top in range(max(0, anchor_top - max_shift), min(height - crop_height, anchor_top + max_shift) + 1):
        candidate_bbox = BoundingBox(
            left=anchor_left,
            top=top,
            right=anchor_left + crop_width,
            bottom=top + crop_height,
        )
        candidate_score = score_tileset_candidate_bbox(
            image_np=image_np,
            candidate_bbox=candidate_bbox,
            tile_size=tile_size,
        )
        if best_score is None or candidate_score > best_score:
            best_score = candidate_score
            best_bbox = candidate_bbox

    return best_bbox


def trim_tileset_bottom_neutral_rows(
    image_np: np.ndarray,
    candidate_bbox: BoundingBox,
    tile_size: int,
) -> BoundingBox:
    crop = rgb_view(image_np[candidate_bbox.top : candidate_bbox.bottom, candidate_bbox.left : candidate_bbox.right])
    neutral_ratio = is_checker_pixel(crop).mean(axis=1)
    bottom_trim = 0
    for ratio in reversed(neutral_ratio):
        if ratio < TILESET_NEUTRAL_ROW_RATIO:
            break
        bottom_trim += 1

    if bottom_trim <= 0 or bottom_trim >= tile_size:
        return candidate_bbox

    new_top = max(0, candidate_bbox.top - bottom_trim)
    new_bottom = candidate_bbox.bottom - bottom_trim
    if new_bottom - new_top != candidate_bbox.height:
        return candidate_bbox

    return BoundingBox(
        left=candidate_bbox.left,
        top=new_top,
        right=candidate_bbox.right,
        bottom=new_bottom,
    )


def trim_tileset_top_noncontent_rows(
    image_np: np.ndarray,
    candidate_bbox: BoundingBox,
    tile_size: int,
) -> BoundingBox:
    crop = rgb_view(image_np[candidate_bbox.top : candidate_bbox.bottom, candidate_bbox.left : candidate_bbox.right])
    neutral_ratio = is_checker_pixel(crop).mean(axis=1)
    light_ratio = is_pale_ui_pixel(crop).mean(axis=1)
    blue_ratio = is_layer1_blue_pixel(crop).mean(axis=1)
    top_trim = 0
    for neutral, light, blue in zip(neutral_ratio, light_ratio, blue_ratio):
        if neutral < TILESET_NEUTRAL_ROW_RATIO and (light + blue) < TILESET_LIGHT_ROW_RATIO:
            break
        top_trim += 1

    if top_trim <= 0 or top_trim >= tile_size:
        return candidate_bbox

    new_top = candidate_bbox.top + top_trim
    new_bottom = min(image_np.shape[0], candidate_bbox.bottom + top_trim)
    if new_bottom - new_top != candidate_bbox.height:
        return candidate_bbox

    return BoundingBox(
        left=candidate_bbox.left,
        top=new_top,
        right=candidate_bbox.right,
        bottom=new_bottom,
    )


def shift_tileset_bbox_up_one_tile(
    image_np: np.ndarray,
    candidate_bbox: BoundingBox,
    tile_size: int,
    workspace_top: int | None = None,
) -> BoundingBox:
    if tile_size <= 0 or candidate_bbox.top < tile_size:
        return candidate_bbox
    if workspace_top is not None and candidate_bbox.top - workspace_top < tile_size:
        return candidate_bbox

    new_top = candidate_bbox.top - tile_size
    new_bottom = candidate_bbox.bottom - tile_size
    if new_bottom > image_np.shape[0]:
        return candidate_bbox

    return BoundingBox(
        left=candidate_bbox.left,
        top=new_top,
        right=candidate_bbox.right,
        bottom=new_bottom,
    )


def align_tileset_bbox_to_tab_left(
    image_np: np.ndarray,
    candidate_bbox: BoundingBox,
    tab_bbox: BoundingBox | None,
) -> BoundingBox:
    if tab_bbox is None or tab_bbox.left >= candidate_bbox.right:
        return candidate_bbox

    aligned_width = candidate_bbox.right - tab_bbox.left
    if aligned_width <= 0 or aligned_width % TILESET_COLUMNS != 0:
        return candidate_bbox

    tile_size = aligned_width // TILESET_COLUMNS
    aligned_top = tab_bbox.bottom + TILESET_TAB_TOP_OFFSET
    aligned_bottom = aligned_top + (tile_size * TILESET_ROWS)
    if tile_size <= 0 or aligned_bottom > image_np.shape[0]:
        return candidate_bbox

    return BoundingBox(
        left=tab_bbox.left,
        top=aligned_top,
        right=candidate_bbox.right,
        bottom=aligned_bottom,
    )


def find_tileset_bbox(
    image_np: np.ndarray,
    workspace_top: int,
    map_bbox: BoundingBox | None = None,
    forced_tile_size: int | None = None,
) -> BoundingBox:
    height, width = image_np.shape[:2]
    map_np = (
        None
        if map_bbox is None
        else rgb_view(image_np[map_bbox.top : map_bbox.bottom, map_bbox.left : map_bbox.right])
    )
    tab_bbox = None
    try:
        tab_bbox = detect_layer1_tab_bbox(image_np, workspace_top)
    except ValueError:
        pass

    anchored_bbox = None
    anchored_score = None
    if forced_tile_size is None and tab_bbox is not None:
        try:
            tile_size = max(1, round(tab_bbox.width / 4))
            left = tab_bbox.left
            top = tab_bbox.bottom + 1
            refined_bbox = refine_anchored_tileset_bbox(
                image_np=image_np,
                anchor_left=left,
                anchor_top=top,
                tile_size=tile_size,
            )
            if refined_bbox is not None:
                refined_bbox = trim_tileset_top_noncontent_rows(image_np, refined_bbox, tile_size)
                anchored_bbox = trim_tileset_bottom_neutral_rows(image_np, refined_bbox, tile_size)
                anchored_score = score_tileset_candidate_bbox(
                    image_np=image_np,
                    candidate_bbox=anchored_bbox,
                    tile_size=tile_size,
                    map_np=map_np,
                )
        except ValueError:
            pass

    search_left = max(0, width - TILESET_SEARCH_WIDTH)
    search_top = detect_tileset_top_boundary(image_np, workspace_top)
    search_bottom = min(height, workspace_top + TILESET_SEARCH_HEIGHT)
    search_region = rgb_view(image_np[search_top:search_bottom, search_left:])
    preview_band_height = min(search_region.shape[0], 140)
    preview_band = search_region[:preview_band_height]
    checker_ratio = is_checker_pixel(preview_band).mean(axis=0)
    light_ratio = is_light_pixel(preview_band).mean(axis=0)
    content_mask = (
        (checker_ratio <= TILESET_EDGE_CHECKER_THRESHOLD)
        & (light_ratio <= TILESET_EDGE_LIGHT_THRESHOLD)
    )

    rough_left = find_first_run(content_mask, TILESET_EDGE_RUN)
    rough_right = find_last_run(content_mask, TILESET_EDGE_RUN)
    if rough_left is None or rough_right is None or rough_right <= rough_left:
        raise ValueError("Could not detect the rough tileset preview bounds in the screenshot.")

    best_bbox = None
    best_score = None
    candidate_tile_sizes = (
        [forced_tile_size]
        if forced_tile_size is not None
        else rank_tileset_tile_sizes(search_region, rough_width=(rough_right - rough_left + 1))
    )
    for tile_size in candidate_tile_sizes:
        crop_height = tile_size * TILESET_ROWS
        max_top_offset = max(0, min((tile_size * 2) - 1, search_bottom - search_top - crop_height))

        for top_offset in range(max_top_offset + 1):
            candidate_top = search_top + top_offset
            candidate_bbox = build_tileset_candidate_bbox(
                image_np=image_np,
                search_left=search_left,
                search_top=candidate_top,
                search_bottom=search_bottom,
                tile_size=tile_size,
            )
            candidate_score = score_tileset_candidate_bbox(
                image_np=image_np,
                candidate_bbox=candidate_bbox,
                tile_size=tile_size,
                map_np=map_np,
            )

            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                best_bbox = candidate_bbox

    if best_bbox is None:
        if anchored_bbox is not None:
            return align_tileset_bbox_to_tab_left(image_np, anchored_bbox, tab_bbox)
        raise ValueError("Could not determine the tileset preview bounds in the screenshot.")

    best_tile_size = best_bbox.width // TILESET_COLUMNS
    best_bbox = trim_tileset_top_noncontent_rows(image_np, best_bbox, best_tile_size)
    best_bbox = trim_tileset_bottom_neutral_rows(image_np, best_bbox, best_tile_size)
    if anchored_bbox is not None and anchored_score is not None:
        best_score = score_tileset_candidate_bbox(
            image_np=image_np,
            candidate_bbox=best_bbox,
            tile_size=best_bbox.width // TILESET_COLUMNS,
            map_np=map_np,
        )
        if anchored_score >= best_score:
            return align_tileset_bbox_to_tab_left(image_np, anchored_bbox, tab_bbox)
    return align_tileset_bbox_to_tab_left(image_np, best_bbox, tab_bbox)


def extract_assets_from_screenshot(
    screenshot_path: Path,
    map_output_path: Path,
    tileset_output_path: Path,
    forced_tileset_tile_size: int | None = None,
    forced_map_tile_size: int | None = None,
) -> tuple[Path, Path, BoundingBox, BoundingBox]:
    screenshot = open_image(screenshot_path)
    screenshot_np = np.array(screenshot)
    workspace_top = detect_workspace_top(screenshot_np)
    map_bbox = find_map_canvas_bbox(screenshot_np, workspace_top)
    screenshot_tile_size = (
        forced_tileset_tile_size
        if forced_tileset_tile_size is not None
        else DEFAULT_SCREENSHOT_TILESET_TILE_SIZE
    )
    screenshot_map_tile_size = (
        forced_map_tile_size
        if forced_map_tile_size is not None
        else DEFAULT_SCREENSHOT_MAP_TILE_SIZE
    )
    tileset_bbox = find_tileset_bbox(
        screenshot_np,
        workspace_top,
        map_bbox=map_bbox,
        forced_tile_size=screenshot_tile_size,
    )
    tile_size = tileset_bbox.width // TILESET_COLUMNS
    tileset_bbox = shift_tileset_bbox_up_one_tile(
        screenshot_np,
        tileset_bbox,
        tile_size,
        workspace_top=workspace_top,
    )
    tileset_np = rgb_view(screenshot_np[tileset_bbox.top : tileset_bbox.bottom, tileset_bbox.left : tileset_bbox.right])
    map_bbox = refine_map_canvas_bbox(screenshot_np, map_bbox, screenshot_map_tile_size, tileset_np=None)

    map_output_path.parent.mkdir(parents=True, exist_ok=True)
    tileset_output_path.parent.mkdir(parents=True, exist_ok=True)
    map_bbox.crop(screenshot).save(map_output_path)
    tileset_bbox.crop(screenshot).save(tileset_output_path)
    return map_output_path, tileset_output_path, map_bbox, tileset_bbox


def infer_tile_size(tileset_np: np.ndarray) -> int:
    height, width = tileset_np.shape[:2]
    if width % TILESET_COLUMNS != 0:
        raise ValueError(
            "Tileset width is not divisible by the expected column count "
            f"({TILESET_COLUMNS}): {width}x{height}"
        )

    tile_width = width // TILESET_COLUMNS
    if height % tile_width != 0:
        raise ValueError(
            "Tileset height is not divisible by the inferred tile size "
            f"({tile_width}): {width}x{height}"
        )

    tile_height = tile_width
    if tile_width != tile_height:
        raise ValueError(f"Tileset tiles are not square: {tile_width}x{tile_height}")
    return tile_width


def split_tiles(tileset_np: np.ndarray, tile_size: int) -> list[np.ndarray]:
    tiles = []
    height, width = tileset_np.shape[:2]
    for y in range(0, height, tile_size):
        for x in range(0, width, tile_size):
            tile = tileset_np[y : y + tile_size, x : x + tile_size]
            if tile.shape[:2] != (tile_size, tile_size):
                continue
            tiles.append(tile)
    return tiles


def resize_tile(tile: np.ndarray, tile_size: int) -> np.ndarray:
    if tile.shape[0] == tile_size and tile.shape[1] == tile_size:
        return tile
    image = Image.fromarray(tile)
    resized = image.resize((tile_size, tile_size), Image.Resampling.NEAREST)
    return np.array(resized)


def ignore_outer_edge_pixels(tile: np.ndarray) -> np.ndarray:
    if tile.shape[0] <= EDGE_IGNORE_MARGIN * 2 or tile.shape[1] <= EDGE_IGNORE_MARGIN * 2:
        return tile
    adjusted = tile.copy()
    adjusted[0, :, :] = adjusted[1, :, :]
    adjusted[-1, :, :] = adjusted[-2, :, :]
    adjusted[:, 0, :] = adjusted[:, 1, :]
    adjusted[:, -1, :] = adjusted[:, -2, :]
    return adjusted


def normalize_tile_for_comparison(tile: np.ndarray, tile_size: int = COMPARISON_TILE_SIZE) -> np.ndarray:
    edge_ignored = ignore_outer_edge_pixels(tile)
    normalized = resize_tile(edge_ignored, tile_size)
    return ignore_outer_edge_pixels(normalized)


def build_map_tiles(tileset_np: np.ndarray, tileset_tile_size: int, map_tile_size: int) -> list[np.ndarray]:
    source_tiles = split_tiles(tileset_np, tileset_tile_size)
    return [resize_tile(tile, map_tile_size) for tile in source_tiles]


def inner_view(tile: np.ndarray, margin: int = INNER_MARGIN) -> np.ndarray:
    if margin <= 0:
        return tile
    return tile[margin:-margin, margin:-margin, :]


def lower_focus_view(tile: np.ndarray) -> np.ndarray:
    height = tile.shape[0]
    top = max(1, height // 2)
    bottom = max(top + 1, height - 2)
    return tile[top:bottom, 1:-1, :]


def structure_view(tile: np.ndarray) -> np.ndarray:
    return tile[1:-2, 1:-1, :]


def edge_intensity_view(tile: np.ndarray) -> np.ndarray:
    gray = grayscale_view(tile)
    horizontal = np.pad(np.abs(np.diff(gray, axis=1)), ((0, 0), (0, 1)))
    vertical = np.pad(np.abs(np.diff(gray, axis=0)), ((0, 1), (0, 0)))
    return horizontal + vertical


def grayscale_projection_signature(tile: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gray = grayscale_view(tile)
    return gray.mean(axis=0), gray.mean(axis=1)


def pooled_rgb_signature(tile: np.ndarray, cells: int = 4) -> np.ndarray:
    image = Image.fromarray(tile)
    pooled = image.resize((cells, cells), Image.Resampling.BILINEAR)
    return np.array(pooled, dtype=np.float32)


def color_signature(tile: np.ndarray) -> np.ndarray:
    inner = tile[1:-1, 1:-1, :3]
    pixels = inner.reshape(-1, 3).astype(np.float32)
    rgb = pixels / 255.0
    hsv = np.array([colorsys.rgb_to_hsv(*pixel) for pixel in rgb], dtype=np.float32) * 255.0
    pooled = pooled_rgb_signature(inner, cells=3).reshape(-1)
    return np.concatenate(
        [
            pixels.mean(axis=0),
            pixels.std(axis=0),
            hsv.mean(axis=0),
            pooled,
        ]
    ).astype(np.float32)


def build_tile_features(tiles: list[np.ndarray]) -> list[TileFeatures]:
    features = []
    for tile in tiles:
        comparable_tile = normalize_tile_for_comparison(tile)
        inner_tile = structure_view(comparable_tile)
        col_signature, row_signature = grayscale_projection_signature(inner_tile)
        block_signature = pooled_rgb_signature(comparable_tile, cells=4)
        center_block_signature = pooled_rgb_signature(comparable_tile[2:-2, 2:-2, :], cells=3)
        lower_block_signature = pooled_rgb_signature(lower_focus_view(comparable_tile), cells=3)
        color_sig = color_signature(comparable_tile)
        features.append(
            TileFeatures(
                tile=comparable_tile,
                inner_tile_i32=inner_tile.astype(np.int32),
                inner_edge_view=edge_intensity_view(inner_tile).astype(np.float32),
                col_signature=col_signature,
                row_signature=row_signature,
                block_signature=block_signature,
                center_block_signature=center_block_signature,
                lower_block_signature=lower_block_signature,
                color_signature=color_sig,
                full_tile_i32=comparable_tile.astype(np.int32),
                left_edge_i32=tile[:, 0, :].astype(np.int32),
                top_edge_i32=tile[0, :, :].astype(np.int32),
            )
        )
    return features


def build_chunk_features(
    chunk: np.ndarray,
    left_tile: np.ndarray | None = None,
    top_tile: np.ndarray | None = None,
) -> ChunkFeatures:
    comparable_chunk = normalize_tile_for_comparison(chunk)
    inner_chunk = structure_view(comparable_chunk)
    col_signature, row_signature = grayscale_projection_signature(inner_chunk)
    block_signature = pooled_rgb_signature(comparable_chunk, cells=4)
    center_block_signature = pooled_rgb_signature(comparable_chunk[2:-2, 2:-2, :], cells=3)
    lower_block_signature = pooled_rgb_signature(lower_focus_view(comparable_chunk), cells=3)
    color_sig = color_signature(comparable_chunk)
    return ChunkFeatures(
        chunk=comparable_chunk,
        inner_chunk_i32=inner_chunk.astype(np.int32),
        inner_edge_view=edge_intensity_view(inner_chunk).astype(np.float32),
        col_signature=col_signature,
        row_signature=row_signature,
        block_signature=block_signature,
        center_block_signature=center_block_signature,
        lower_block_signature=lower_block_signature,
        color_signature=color_sig,
        full_chunk_i32=comparable_chunk.astype(np.int32),
        left_neighbor_edge_i32=(
            left_tile[:, -1, :].astype(np.int32) if left_tile is not None else None
        ),
        top_neighbor_edge_i32=(
            top_tile[-1, :, :].astype(np.int32) if top_tile is not None else None
        ),
    )


def boundary_match_score(
    tile_features: TileFeatures,
    left_edge_i32: np.ndarray | None = None,
    top_edge_i32: np.ndarray | None = None,
) -> int:
    score = 0

    if left_edge_i32 is not None:
        left_diff = left_edge_i32 - tile_features.left_edge_i32
        score += int(np.abs(left_diff).sum())

    if top_edge_i32 is not None:
        top_diff = top_edge_i32 - tile_features.top_edge_i32
        score += int(np.abs(top_diff).sum())

    return score


def combined_similarity_score(
    *,
    inner_score: int,
    center_score: int,
    lower_block_score: int,
    block_score: int,
    color_score: int,
    edge_score: int,
    profile_score: int,
    full_score: int,
    neighbor_score: int,
) -> float:
    return (
        (inner_score * INNER_SCORE_WEIGHT)
        + (center_score * CENTER_SCORE_WEIGHT)
        + (lower_block_score * LOWER_BLOCK_SCORE_WEIGHT)
        + (block_score * BLOCK_SCORE_WEIGHT)
        + (color_score * COLOR_SCORE_WEIGHT)
        + (edge_score * EDGE_SCORE_WEIGHT)
        + (profile_score * PROFILE_SCORE_WEIGHT)
        + (full_score * FULL_SCORE_WEIGHT)
        + (neighbor_score * NEIGHBOR_SCORE_WEIGHT)
    )


def find_tile(
    chunk: np.ndarray,
    tiles: list[np.ndarray],
    left_tile: np.ndarray | None = None,
    top_tile: np.ndarray | None = None,
    tile_features: list[TileFeatures] | None = None,
    chunk_features: ChunkFeatures | None = None,
    preferred_tile_ids: set[int] | None = None,
) -> tuple[int, str, int]:
    computed_chunk_features = (
        chunk_features
        if chunk_features is not None
        else build_chunk_features(chunk, left_tile=left_tile, top_tile=top_tile)
    )
    candidate_features = tile_features if tile_features is not None else build_tile_features(tiles)
    scored_tiles = []

    for index, feature in enumerate(candidate_features):
        preferred_rank = 0 if preferred_tile_ids is None or (index + 1) in preferred_tile_ids else 1
        diff = computed_chunk_features.inner_chunk_i32 - feature.inner_tile_i32
        inner_score = int(np.abs(diff).sum())

        edge_diff = computed_chunk_features.inner_edge_view - feature.inner_edge_view
        edge_score = int(np.abs(edge_diff).sum())

        profile_score = int(
            np.abs(computed_chunk_features.col_signature - feature.col_signature).sum()
            + np.abs(computed_chunk_features.row_signature - feature.row_signature).sum()
        )
        block_score = int(
            np.abs(computed_chunk_features.block_signature - feature.block_signature).sum()
        )
        center_score = int(
            np.abs(computed_chunk_features.center_block_signature - feature.center_block_signature).sum()
        )
        lower_block_score = int(
            np.abs(computed_chunk_features.lower_block_signature - feature.lower_block_signature).sum()
        )
        color_score = int(
            np.abs(computed_chunk_features.color_signature - feature.color_signature).sum()
        )

        full_diff = computed_chunk_features.full_chunk_i32 - feature.full_tile_i32
        full_score = int(np.abs(full_diff).sum())
        neighbor_score = boundary_match_score(
            feature,
            left_edge_i32=computed_chunk_features.left_neighbor_edge_i32,
            top_edge_i32=computed_chunk_features.top_neighbor_edge_i32,
        )
        combined_score = combined_similarity_score(
            inner_score=inner_score,
            center_score=center_score,
            lower_block_score=lower_block_score,
            block_score=block_score,
            color_score=color_score,
            edge_score=edge_score,
            profile_score=profile_score,
            full_score=full_score,
            neighbor_score=neighbor_score,
        )
        scored_tiles.append(
            (
                index + 1,
                preferred_rank,
                combined_score,
                inner_score,
                center_score,
                lower_block_score,
                color_score,
                edge_score,
                block_score,
                profile_score,
                full_score,
                neighbor_score,
            )
        )

    if not scored_tiles:
        raise ValueError(f"No valid tiles found for chunk shape {chunk.shape}")

    scored_tiles.sort(key=lambda item: (item[2], item[1], item[4], item[5], item[6], item[7], item[9], item[8], item[10], item[11], item[3], item[0]))
    neighbor_context_available = left_tile is not None or top_tile is not None
    if neighbor_context_available:
        chosen_tile_id, _, chosen_combined_score, chosen_inner_score, chosen_center_score, chosen_lower_block_score, chosen_color_score, chosen_edge_score, chosen_block_score, chosen_profile_score, _, chosen_neighbor_score = min(
            scored_tiles,
            key=lambda item: (item[2], item[11], item[1], item[4], item[5], item[6], item[7], item[9], item[8], item[10], item[3], item[0]),
        )
    else:
        chosen_tile_id, _, chosen_combined_score, chosen_inner_score, chosen_center_score, chosen_lower_block_score, chosen_color_score, chosen_edge_score, chosen_block_score, chosen_profile_score, _, chosen_neighbor_score = scored_tiles[0]
    match_mode = "inner_exact" if chosen_inner_score == 0 and chosen_edge_score == 0 else "nearest"
    return (
        chosen_tile_id,
        match_mode,
        int(round(chosen_combined_score)),
    )


def derive_output_paths(map_path: Path) -> OutputPaths:
    stem = map_path.stem
    base_stem = stem[:-4] if stem.endswith("_map") else stem
    return {
        "comparison": map_path.with_name(f"{base_stem}_comparison.png"),
        "csv": map_path.with_name(f"{base_stem}_tiles.csv"),
    }


def infer_map_stem(map_path: Path) -> str:
    return map_path.stem[:-4] if map_path.stem.endswith("_map") else map_path.stem


def infer_map_grid_dimensions(
    source_width: int,
    source_height: int,
    map_offset_x: int,
    map_offset_y: int,
    tile_size: int,
) -> tuple[int, int]:
    usable_width = source_width - map_offset_x
    usable_height = source_height - map_offset_y
    if usable_width <= 0 or usable_height <= 0:
        raise ValueError("Map offset is outside the image bounds.")
    return usable_width // tile_size, usable_height // tile_size


def analyze_map(
    map_path: Path,
    tileset_path: Path,
    map_offset_x: int,
    map_offset_y: int,
    map_tile_columns: int | None,
    map_tile_rows: int | None,
    map_tile_size: int | None,
) -> AnalyzeSummary:
    tileset = open_image(tileset_path)
    map_img = open_image(map_path)
    tileset_np = np.array(tileset)
    source_map_np = np.array(map_img)
    tileset_tile_size = infer_tile_size(tileset_np)
    detected_map_tile_size = detect_map_tile_size(rgb_view(source_map_np))
    tile_size = map_tile_size if map_tile_size is not None else detected_map_tile_size
    match_tiles = build_map_tiles(tileset_np, tileset_tile_size=tileset_tile_size, map_tile_size=tile_size)
    tile_features = build_tile_features(match_tiles)

    source_height, source_width = source_map_np.shape[:2]
    available_columns, available_rows = infer_map_grid_dimensions(
        source_width=source_width,
        source_height=source_height,
        map_offset_x=map_offset_x,
        map_offset_y=map_offset_y,
        tile_size=tile_size,
    )
    tile_columns = map_tile_columns if map_tile_columns is not None else available_columns
    tile_rows = map_tile_rows if map_tile_rows is not None else available_rows
    tile_columns = min(tile_columns, available_columns)
    tile_rows = min(tile_rows, available_rows)

    cropped_width = tile_columns * tile_size
    cropped_height = tile_rows * tile_size
    map_np = source_map_np[
        map_offset_y : map_offset_y + cropped_height,
        map_offset_x : map_offset_x + cropped_width,
    ]
    height, width = map_np.shape[:2]

    result: list[list[int]] = []
    debug_rows: list[list[DebugCell]] = []
    reconstructed_rows = []

    for y in range(0, height, tile_size):
        row = []
        debug_row = []
        reconstructed_row = []
        row_index = y // tile_size
        for x in range(0, width, tile_size):
            chunk = map_np[y : y + tile_size, x : x + tile_size]
            column_index = x // tile_size
            left_tile = reconstructed_row[column_index - 1] if column_index > 0 else None
            top_tile = (
                reconstructed_rows[row_index - 1][column_index]
                if row_index > 0
                else None
            )
            chunk_features = build_chunk_features(
                chunk,
                left_tile=left_tile,
                top_tile=top_tile,
            )
            tile_id, match_mode, score = find_tile(
                chunk,
                match_tiles,
                left_tile=left_tile,
                top_tile=top_tile,
                tile_features=tile_features,
                chunk_features=chunk_features,
            )
            row.append(tile_id)
            debug_row.append(DebugCell(tile_id=tile_id, mode=match_mode, score=score))
            reconstructed_row.append(match_tiles[tile_id - 1])
        result.append(row)
        debug_rows.append(debug_row)
        reconstructed_rows.append(reconstructed_row)

    reconstructed = np.zeros_like(map_np)
    for row_index, reconstructed_row in enumerate(reconstructed_rows):
        for column_index, tile in enumerate(reconstructed_row):
            y = row_index * tile_size
            x = column_index * tile_size
            reconstructed[y : y + tile_size, x : x + tile_size] = tile

    output_paths = derive_output_paths(map_path)
    reconstructed_img = Image.fromarray(reconstructed)

    cropped_map_img = Image.fromarray(map_np)
    comparison = Image.new("RGBA", (cropped_map_img.width * 2, cropped_map_img.height), (0, 0, 0, 255))
    comparison.paste(cropped_map_img, (0, 0))
    comparison.paste(reconstructed_img, (cropped_map_img.width, 0))
    comparison.save(output_paths["comparison"])

    with output_paths["csv"].open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(result)

    # with map_path.with_name(f"{map_path.stem}_tiles_debug.csv").open("w", newline="", encoding="utf-8") as csv_file:
    #     writer = csv.writer(csv_file)
    #     writer.writerow(["row", "col", "tile_id", "mode", "score"])
    #     for row_index, row in enumerate(debug_rows):
    #         for col_index, cell in enumerate(row):
    #             writer.writerow(
    #                 [
    #                     row_index,
    #                     col_index,
    #                     cell["tile_id"],
    #                     cell["mode"],
    #                     cell["score"],
    #                 ]
    #             )

    # suspicious_img = cropped_map_img.copy()
    # suspicious_overlay = Image.new("RGBA", cropped_map_img.size, (0, 0, 0, 0))
    # suspicious_np = np.array(suspicious_overlay)
    # for row_index, row in enumerate(debug_rows):
    #     for col_index, cell in enumerate(row):
    #         if cell["mode"] != "nearest" or cell["score"] < SUSPICIOUS_SCORE_THRESHOLD:
    #             continue
    #         y = row_index * tile_size
    #         x = col_index * tile_size
    #         suspicious_np[y : y + tile_size, x : x + tile_size] = np.array([255, 0, 0, 96], dtype=np.uint8)
    #
    # suspicious_overlay = Image.fromarray(suspicious_np, mode="RGBA")
    # suspicious_img.alpha_composite(suspicious_overlay)
    # suspicious_img.save(map_path.with_name(f"{map_path.stem}_suspicious_tiles.png"))

    return {
        "result": result,
        "debug_rows": debug_rows,
        "tile_size": tile_size,
        "tileset_tile_size": tileset_tile_size,
        "output_paths": output_paths,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a map canvas and a tileset from a screenshot when needed, "
            "then match the map against the tileset and write tile ids to CSV."
        )
    )
    parser.add_argument("--screenshot", type=Path, help="FF6Tools screenshot to extract from.")
    parser.add_argument(
        "--screenshot-tileset-tile-size",
        type=int,
        help="Override the screenshot tileset tile size. Defaults to 38px when omitted.",
    )
    parser.add_argument("--map-name", help="Output map canvas name without extension.")
    parser.add_argument("--tileset-name", help="Output tileset name without extension.")
    parser.add_argument("--map-path", type=Path, default=DEFAULT_MAP_PATH, help="Input map image path.")
    parser.add_argument(
        "--tileset-path",
        type=Path,
        default=DEFAULT_TILESET_PATH,
        help="Input tileset image path.",
    )
    parser.add_argument("--map-offset-x", type=int, default=DEFAULT_MAP_OFFSET_X)
    parser.add_argument("--map-offset-y", type=int, default=DEFAULT_MAP_OFFSET_Y)
    parser.add_argument("--map-tile-columns", type=int, default=DEFAULT_MAP_TILE_COLUMNS)
    parser.add_argument("--map-tile-rows", type=int, default=DEFAULT_MAP_TILE_ROWS)
    parser.add_argument("--map-tile-size", type=int, help="Override the map canvas tile size used for matching.")
    return parser


def resolve_output_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.screenshot is None:
        return args.map_path, args.tileset_path

    screenshot_stem = args.screenshot.stem
    map_name = args.map_name or f"{screenshot_stem}_map"
    tileset_name = args.tileset_name or screenshot_stem
    map_path = BASE_DIR / f"{map_name}.png"
    tileset_path = BASE_DIR / "TILESET" / f"TILESET - {tileset_name}.png"
    return map_path, tileset_path


def print_results(summary: AnalyzeSummary, map_path: Path, tileset_path: Path) -> None:
    result = summary["result"]
    debug_rows = summary["debug_rows"]
    output_paths = summary["output_paths"]

    print(f"# map: {map_path}")
    print(f"# tileset: {tileset_path}")
    print(f"# map_tile_size: {summary['tile_size']}")
    print(f"# tileset_tile_size: {summary['tileset_tile_size']}")
    print()
    for row in result:
        print(row)

    print()
    print("# debug")
    for row in debug_rows:
        print([f"{cell['tile_id']}:{cell['mode']}:{cell['score']}" for cell in row])

    print()
    print(f"# comparison_image: {output_paths['comparison']}")
    print(f"# csv: {output_paths['csv']}")
    # print(f"# debug_csv: {map_path.with_name(f'{map_path.stem}_tiles_debug.csv')}")
    # print(f"# suspicious_tiles_image: {map_path.with_name(f'{map_path.stem}_suspicious_tiles.png')}")


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    map_path, tileset_path = resolve_output_paths(args)
    effective_map_tile_size = (
        args.map_tile_size
        if args.map_tile_size is not None
        else (DEFAULT_SCREENSHOT_MAP_TILE_SIZE if args.screenshot is not None else None)
    )

    if args.screenshot is not None:
        _, _, map_bbox, tileset_bbox = extract_assets_from_screenshot(
            screenshot_path=args.screenshot,
            map_output_path=map_path,
            tileset_output_path=tileset_path,
            forced_tileset_tile_size=args.screenshot_tileset_tile_size,
            forced_map_tile_size=effective_map_tile_size,
        )
        print(f"# extracted_map_bbox: {map_bbox}")
        print(f"# extracted_tileset_bbox: {tileset_bbox}")

    summary = analyze_map(
        map_path=map_path,
        tileset_path=tileset_path,
        map_offset_x=args.map_offset_x,
        map_offset_y=args.map_offset_y,
        map_tile_columns=args.map_tile_columns,
        map_tile_rows=args.map_tile_rows,
        map_tile_size=effective_map_tile_size,
    )
    print_results(summary, map_path=map_path, tileset_path=tileset_path)


if __name__ == "__main__":
    main()
