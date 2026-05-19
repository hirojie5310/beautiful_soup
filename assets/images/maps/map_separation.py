from __future__ import annotations

import argparse
import csv
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import numpy as np
from PIL import Image

INNER_MARGIN = 1
SUSPICIOUS_SCORE_THRESHOLD = 500
INNER_SCORE_TIE_THRESHOLD = 32
DEFAULT_MAP_OFFSET_X = 0
DEFAULT_MAP_OFFSET_Y = 0
DEFAULT_MAP_TILE_COLUMNS = None
DEFAULT_MAP_TILE_ROWS = None
TILESET_COLUMNS = 16
TILESET_ROWS = 8
WORKSPACE_TOP_SEARCH_LIMIT = 120
TILESET_SEARCH_HEIGHT = 300
TILESET_SEARCH_WIDTH = 560
TILESET_TAB_SEARCH_HEIGHT = 90
TILESET_TAB_SEARCH_WIDTH = 220
TILESET_TAB_BLUE_THRESHOLD = 0.1
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
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TILESET_PATH = BASE_DIR / "TILESET" / "TILESET - SealedCave.png"
DEFAULT_MAP_PATH = BASE_DIR / "Sealed_Cave_B2_2.png"


class OutputPaths(TypedDict):
    reconstructed: Path
    comparison: Path
    csv: Path
    debug_csv: Path
    suspicious: Path


class DebugCell(TypedDict):
    tile_id: int
    mode: str
    score: int


class AnalyzeSummary(TypedDict):
    result: list[list[int]]
    debug_rows: list[list[DebugCell]]
    tile_size: int
    output_paths: OutputPaths


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


def is_checker_pixel(rgb: np.ndarray) -> np.ndarray:
    spread = rgb.max(axis=-1) - rgb.min(axis=-1)
    mean = rgb.mean(axis=-1)
    return np.asarray((spread <= 8) & (mean >= 38) & (mean <= 62))


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
        large_green_components = [
            bbox
            for area, bbox in green_components
            if area >= MAP_COMPONENT_MIN_AREA
            and max(bbox.width, bbox.height) >= MAP_COMPONENT_MIN_SIDE
            and min(bbox.width, bbox.height) >= MAP_COMPONENT_MIN_THICKNESS
        ]
        if large_green_components:
            component_bbox = BoundingBox(
                left=min(bbox.left for bbox in large_green_components),
                top=min(bbox.top for bbox in large_green_components),
                right=max(bbox.right for bbox in large_green_components),
                bottom=max(bbox.bottom for bbox in large_green_components),
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


def refine_map_canvas_bbox(image_np: np.ndarray, map_bbox: BoundingBox, tile_size: int) -> BoundingBox:
    map_region = rgb_view(image_np[map_bbox.top : map_bbox.bottom, map_bbox.left : map_bbox.right])
    mean = map_region.mean(axis=-1)
    spread = map_region.max(axis=-1) - map_region.min(axis=-1)
    black_mask = mean <= MAP_BLACK_THRESHOLD
    checker_mask = (spread <= 8) & (mean >= 38) & (mean <= 62)
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
        col_start += left_margin

    significant_rows = np.where(row_counts[row_start:row_end] >= row_threshold)[0]
    significant_cols = np.where(col_counts[col_start:col_end] >= col_threshold)[0]
    if len(significant_rows) == 0 or len(significant_cols) == 0:
        return map_bbox

    row_start += int(significant_rows[0])
    row_end = row_start + int(significant_rows[-1] - significant_rows[0]) + 1
    col_start += int(significant_cols[0])
    col_end = col_start + int(significant_cols[-1] - significant_cols[0]) + 1

    raw_width = col_end - col_start
    raw_height = row_end - row_start
    refined_width = floor_length_to_tile(raw_width, tile_size)
    refined_height = floor_length_to_tile(raw_height, tile_size)
    if refined_width < tile_size:
        refined_width = snap_length_to_tile(raw_width, tile_size)
    if refined_height < tile_size:
        refined_height = snap_length_to_tile(raw_height, tile_size)

    refined_right = min(map_bbox.width, col_start + refined_width)
    refined_bottom = min(map_bbox.height, row_start + refined_height)
    if refined_right - col_start < tile_size or refined_bottom - row_start < tile_size:
        return map_bbox

    return BoundingBox(
        left=map_bbox.left + col_start,
        top=map_bbox.top + row_start,
        right=map_bbox.left + refined_right,
        bottom=map_bbox.top + refined_bottom,
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


def detect_tileset_tile_size(search_region: np.ndarray, rough_width: int) -> int:
    max_tile_size = min(search_region.shape[1] // TILESET_COLUMNS, search_region.shape[0] // TILESET_ROWS)
    if max_tile_size <= 0:
        raise ValueError("Search region is too small to contain the tileset preview.")

    min_tile_size = 8
    max_candidate = max_tile_size

    gray = grayscale_view(search_region)
    intensity_col_signal = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    intensity_row_signal = np.abs(np.diff(gray, axis=0)).mean(axis=1)
    edge_col_signal, edge_row_signal = edge_projection_signals(search_region)

    candidate_scores = []
    for tile_size in range(min_tile_size, max_candidate + 1):
        intensity_score = periodicity_score(intensity_col_signal, intensity_row_signal, tile_size)
        edge_score = periodicity_score(edge_col_signal, edge_row_signal, tile_size)
        combined_score = intensity_score + edge_score
        candidate_scores.append((combined_score, tile_size))

    if not candidate_scores:
        raise ValueError("Could not derive any tile-size candidates from the tileset preview.")

    best_score = max(score for score, _ in candidate_scores)
    near_best = [
        (score, tile_size)
        for score, tile_size in candidate_scores
        if score >= best_score * 0.98
    ]
    return max(tile_size for _, tile_size in near_best)


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


def detect_layer1_tab_bbox(image_np: np.ndarray) -> BoundingBox:
    height, width = image_np.shape[:2]
    panel_left = max(0, width - TILESET_SEARCH_WIDTH)
    panel_top = 0
    panel_right = width
    panel_bottom = min(height, TILESET_TAB_SEARCH_HEIGHT)
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
            _, match_mode, score = find_tile(chunk, tiles)
            total_score += score
            exact_matches += int(match_mode == "inner_exact")
            sample_count += 1

    if sample_count == 0:
        return float("-inf")

    average_score = total_score / sample_count
    return -average_score + (exact_matches * 250.0)


def refine_tileset_left(search_region: np.ndarray, rough_left: int, tile_size: int) -> int:
    crop_width = tile_size * TILESET_COLUMNS
    crop_height = tile_size * TILESET_ROWS
    max_left = search_region.shape[1] - crop_width
    left_start = max(0, rough_left)
    left_end = min(max_left, rough_left + tile_size - 1)

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
        raise ValueError("Could not refine the tileset left edge.")
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


def find_tileset_bbox(
    image_np: np.ndarray,
    workspace_top: int,
    map_bbox: BoundingBox | None = None,
) -> BoundingBox:
    height, width = image_np.shape[:2]
    try:
        tab_bbox = detect_layer1_tab_bbox(image_np)
        tile_size = max(1, round(tab_bbox.width / 4))
        left = tab_bbox.left
        top = tab_bbox.bottom + 1
        right = left + (tile_size * TILESET_COLUMNS)
        bottom = top + (tile_size * TILESET_ROWS)
        if right <= width and bottom <= height:
            return BoundingBox(left=left, top=top, right=right, bottom=bottom)
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

    tile_size = detect_tileset_tile_size(search_region, rough_width=(rough_right - rough_left + 1))
    crop_height = tile_size * TILESET_ROWS
    max_top_offset = max(0, min(tile_size - 1, search_bottom - search_top - crop_height))
    map_np = None if map_bbox is None else image_np[map_bbox.top : map_bbox.bottom, map_bbox.left : map_bbox.right]

    best_bbox = None
    best_score = None
    for top_offset in range(max_top_offset + 1):
        candidate_top = search_top + top_offset
        candidate_bbox = build_tileset_candidate_bbox(
            image_np=image_np,
            search_left=search_left,
            search_top=candidate_top,
            search_bottom=search_bottom,
            tile_size=tile_size,
        )
        candidate_crop = rgb_view(
            image_np[
                candidate_bbox.top : candidate_bbox.bottom,
                candidate_bbox.left : candidate_bbox.right,
            ]
        )
        candidate_score = score_tileset_crop(candidate_crop, tile_size)
        if map_np is not None:
            candidate_score += score_tileset_against_map(
                map_np,
                image_np[
                    candidate_bbox.top : candidate_bbox.bottom,
                    candidate_bbox.left : candidate_bbox.right,
                ],
                tile_size,
            )

        if best_score is None or candidate_score > best_score:
            best_score = candidate_score
            best_bbox = candidate_bbox

    if best_bbox is None:
        raise ValueError("Could not determine the tileset preview bounds in the screenshot.")

    return best_bbox


def extract_assets_from_screenshot(
    screenshot_path: Path,
    map_output_path: Path,
    tileset_output_path: Path,
) -> tuple[Path, Path, BoundingBox, BoundingBox]:
    screenshot = open_image(screenshot_path)
    screenshot_np = np.array(screenshot)
    workspace_top = detect_workspace_top(screenshot_np)
    map_bbox = find_map_canvas_bbox(screenshot_np, workspace_top)
    tileset_bbox = find_tileset_bbox(screenshot_np, workspace_top, map_bbox=map_bbox)
    tile_size = tileset_bbox.width // TILESET_COLUMNS
    map_bbox = refine_map_canvas_bbox(screenshot_np, map_bbox, tile_size)

    map_output_path.parent.mkdir(parents=True, exist_ok=True)
    tileset_output_path.parent.mkdir(parents=True, exist_ok=True)
    map_bbox.crop(screenshot).save(map_output_path)
    tileset_bbox.crop(screenshot).save(tileset_output_path)
    return map_output_path, tileset_output_path, map_bbox, tileset_bbox


def infer_tile_size(tileset_np: np.ndarray) -> int:
    height, width = tileset_np.shape[:2]
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


def inner_view(tile: np.ndarray, margin: int = INNER_MARGIN) -> np.ndarray:
    if margin <= 0:
        return tile
    return tile[margin:-margin, margin:-margin, :]


def find_tile(
    chunk: np.ndarray,
    tiles: list[np.ndarray],
) -> tuple[int, str, int]:
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


def derive_output_paths(map_path: Path) -> OutputPaths:
    stem = map_path.stem
    return {
        "reconstructed": map_path.with_name(f"{stem}_reconstructed.png"),
        "comparison": map_path.with_name(f"{stem}_comparison.png"),
        "csv": map_path.with_name(f"{stem}_tiles.csv"),
        "debug_csv": map_path.with_name(f"{stem}_tiles_debug.csv"),
        "suspicious": map_path.with_name(f"{stem}_suspicious_tiles.png"),
    }


def analyze_map(
    map_path: Path,
    tileset_path: Path,
    map_offset_x: int,
    map_offset_y: int,
    map_tile_columns: int | None,
    map_tile_rows: int | None,
) -> AnalyzeSummary:
    tileset = open_image(tileset_path)
    map_img = open_image(map_path)
    tileset_np = np.array(tileset)
    source_map_np = np.array(map_img)
    tile_size = infer_tile_size(tileset_np)
    tiles = split_tiles(tileset_np, tile_size)

    source_height, source_width = source_map_np.shape[:2]
    available_columns = (source_width - map_offset_x) // tile_size
    available_rows = (source_height - map_offset_y) // tile_size
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
        for x in range(0, width, tile_size):
            chunk = map_np[y : y + tile_size, x : x + tile_size]
            tile_id, match_mode, score = find_tile(chunk, tiles)
            row.append(tile_id)
            debug_row.append(DebugCell(tile_id=tile_id, mode=match_mode, score=score))
            reconstructed_row.append(tiles[tile_id - 1])
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
    reconstructed_img.save(output_paths["reconstructed"])

    cropped_map_img = Image.fromarray(map_np)
    comparison = Image.new("RGBA", (cropped_map_img.width * 2, cropped_map_img.height), (0, 0, 0, 255))
    comparison.paste(cropped_map_img, (0, 0))
    comparison.paste(reconstructed_img, (cropped_map_img.width, 0))
    comparison.save(output_paths["comparison"])

    with output_paths["csv"].open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(result)

    with output_paths["debug_csv"].open("w", newline="", encoding="utf-8") as csv_file:
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
            y = row_index * tile_size
            x = col_index * tile_size
            suspicious_np[y : y + tile_size, x : x + tile_size] = np.array([255, 0, 0, 96], dtype=np.uint8)

    suspicious_overlay = Image.fromarray(suspicious_np, mode="RGBA")
    suspicious_img.alpha_composite(suspicious_overlay)
    suspicious_img.save(output_paths["suspicious"])

    return {
        "result": result,
        "debug_rows": debug_rows,
        "tile_size": tile_size,
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
    return parser


def resolve_output_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.screenshot is None:
        return args.map_path, args.tileset_path

    map_name = args.map_name or args.screenshot.stem
    tileset_name = args.tileset_name or map_name
    map_path = BASE_DIR / f"{map_name}.png"
    tileset_path = BASE_DIR / "TILESET" / f"TILESET - {tileset_name}.png"
    return map_path, tileset_path


def print_results(summary: AnalyzeSummary, map_path: Path, tileset_path: Path) -> None:
    result = summary["result"]
    debug_rows = summary["debug_rows"]
    output_paths = summary["output_paths"]

    print(f"# map: {map_path}")
    print(f"# tileset: {tileset_path}")
    print(f"# tile_size: {summary['tile_size']}")
    print()
    for row in result:
        print(row)

    print()
    print("# debug")
    for row in debug_rows:
        print([f"{cell['tile_id']}:{cell['mode']}:{cell['score']}" for cell in row])

    print()
    print(f"# reconstructed_image: {output_paths['reconstructed']}")
    print(f"# comparison_image: {output_paths['comparison']}")
    print(f"# csv: {output_paths['csv']}")
    print(f"# debug_csv: {output_paths['debug_csv']}")
    print(f"# suspicious_tiles_image: {output_paths['suspicious']}")


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    map_path, tileset_path = resolve_output_paths(args)

    if args.screenshot is not None:
        _, _, map_bbox, tileset_bbox = extract_assets_from_screenshot(
            screenshot_path=args.screenshot,
            map_output_path=map_path,
            tileset_output_path=tileset_path,
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
    )
    print_results(summary, map_path=map_path, tileset_path=tileset_path)


if __name__ == "__main__":
    main()
