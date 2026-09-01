#!/usr/bin/env python3
"""Deterministic bitmap checks used by the WeChat visual workflow."""

from __future__ import annotations

import hashlib
import math
import re
import struct
import zlib
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ROLE_ASPECT_RATIOS = {
    "floating-spot": (0.75, 1.34),
    "section-transition": (2.2, 6.0),
    "inline-explainer": (1.1, 2.0),
    "closing-motif": (0.75, 1.34),
}
ROLE_MINIMUM_CANVAS_COVERAGE = {
    # Micro assets are subject cut-outs.  Whitespace belongs to the Ardot layout,
    # not to a huge transparent bitmap canvas.
    "floating-spot": (0.62, 0.62),
    "section-transition": (0.72, 0.40),
    "inline-explainer": (0.60, 0.54),
    "closing-motif": (0.62, 0.62),
}
MICRO_CUTOUT_EVIDENCE_FIELDS = (
    "alpha_visible_bbox",
    "alpha_bbox_fill_ratio",
    "alpha_bbox_canvas_fill_ratio",
    "alpha_padding_ratio",
    "alpha_substantive_pixel_count",
    "alpha_substantive_total_pixel_count",
    "alpha_largest_component_ratio",
    "alpha_ignored_fly_pixel_count",
    "alpha_touches_canvas_edge",
    "alpha_matte_color_ratio",
    "alpha_near_white_ratio",
    "alpha_dominant_color_ratio",
    "alpha_partial_pixel_count",
    "alpha_near_white_halo_ratio",
    "alpha_near_black_halo_ratio",
)
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def _decoded_png_rows(path: Path) -> tuple[int, int, int, list[bytearray]]:
    """Decode ordinary 8-bit non-interlaced PNG rows without third-party libraries."""
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("asset must be a PNG file")
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        chunks.append((chunk_type, chunk_data))
        offset += 12 + length
        if chunk_type == b"IEND":
            break
    ihdr = next((value for kind, value in chunks if kind == b"IHDR"), None)
    if ihdr is None or len(ihdr) != 13:
        raise ValueError("PNG is missing a valid IHDR chunk")
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    channels = channels_by_type.get(color_type)
    if (
        width <= 0
        or height <= 0
        or bit_depth != 8
        or channels is None
        or compression != 0
        or filtering != 0
        or interlace != 0
    ):
        raise ValueError("PNG color analysis requires 8-bit non-interlaced RGB/RGBA/grayscale")
    stride = width * channels
    compressed = b"".join(value for kind, value in chunks if kind == b"IDAT")
    try:
        raw = zlib.decompress(compressed)
    except zlib.error as exc:
        raise ValueError(f"PNG IDAT data cannot be decompressed: {exc}") from exc
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG scanline data has an unexpected length")
    rows: list[bytearray] = []
    prior = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        encoded = raw[cursor : cursor + stride]
        cursor += stride
        decoded = bytearray(stride)
        for index, value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            above = prior[index]
            upper_left = prior[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise ValueError(f"unsupported PNG filter type: {filter_type}")
            decoded[index] = (value + predictor) & 0xFF
        rows.append(decoded)
        prior = decoded
    return width, height, channels, rows


def _relative_luminance(red: int, green: int, blue: int) -> float:
    def channel(value: int) -> float:
        normalized = value / 255
        return normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def _hex_luminance(value: str) -> float:
    if not HEX_COLOR.fullmatch(value):
        raise ValueError("body_text_color must be a #RRGGBB color")
    return _relative_luminance(*(int(value[index : index + 2], 16) for index in (1, 3, 5)))


def _largest_extreme_region(cell_counts: list[list[list[int]]], kind_index: int) -> float:
    height = len(cell_counts)
    width = len(cell_counts[0]) if height else 0
    extreme = {
        (row, column)
        for row in range(height)
        for column in range(width)
        if cell_counts[row][column][0] > 0
        and cell_counts[row][column][kind_index] / cell_counts[row][column][0] >= 0.85
    }
    total = sum(cell[0] for row in cell_counts for cell in row) or 1
    largest = 0
    while extreme:
        start = extreme.pop()
        stack = [start]
        region = 0
        while stack:
            row, column = stack.pop()
            region += cell_counts[row][column][0]
            for neighbor in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)):
                if neighbor in extreme:
                    extreme.remove(neighbor)
                    stack.append(neighbor)
        largest = max(largest, region)
    return round(largest / total, 6)


def inspect_background_asset(
    path: Path,
    copy_safe_zone: dict[str, Any],
    body_text_color: str,
) -> dict[str, Any]:
    """Measure family continuity and text safety from actual background pixels."""
    width, height, channels, rows = _decoded_png_rows(path)
    for field in ("x", "y", "width", "height"):
        value = copy_safe_zone.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"copy_safe_zone.{field} must be numeric")
    zone_x = float(copy_safe_zone["x"])
    zone_y = float(copy_safe_zone["y"])
    zone_w = float(copy_safe_zone["width"])
    zone_h = float(copy_safe_zone["height"])
    if not 0 <= zone_x < 1 or not 0 <= zone_y < 1 or zone_w <= 0 or zone_h <= 0:
        raise ValueError("copy_safe_zone must use positive normalized coordinates")
    if zone_x + zone_w > 1 or zone_y + zone_h > 1:
        raise ValueError("copy_safe_zone must remain within the background bounds")
    text_luminance = _hex_luminance(body_text_color)
    sample_step = max(1, math.ceil(math.sqrt((width * height) / 250_000)))
    grid_size = 12
    cells = [[[0, 0, 0] for _ in range(grid_size)] for _ in range(grid_size)]
    spatial_sums = [[0.0 for _ in range(grid_size)] for _ in range(grid_size)]
    spatial_counts = [[0 for _ in range(grid_size)] for _ in range(grid_size)]
    horizontal_gradient_total = vertical_gradient_total = 0.0
    horizontal_gradient_count = vertical_gradient_count = 0
    previous_sample_row: list[float] | None = None
    luminances: list[float] = []
    zone_luminances: list[float] = []
    red_total = green_total = blue_total = 0
    dark = light = non_opaque = samples = 0
    zone_left = int(zone_x * width)
    zone_top = int(zone_y * height)
    zone_right = max(zone_left + 1, int((zone_x + zone_w) * width))
    zone_bottom = max(zone_top + 1, int((zone_y + zone_h) * height))
    for y in range(0, height, sample_step):
        row = rows[y]
        current_sample_row: list[float] = []
        previous_luminance: float | None = None
        for x in range(0, width, sample_step):
            offset = x * channels
            if channels in {1, 2}:
                red = green = blue = row[offset]
            else:
                red, green, blue = row[offset : offset + 3]
            if channels in {2, 4}:
                non_opaque += int(row[offset + channels - 1] < 255)
            luminance = _relative_luminance(red, green, blue)
            luminances.append(luminance)
            current_sample_row.append(luminance)
            if previous_luminance is not None:
                horizontal_gradient_total += abs(luminance - previous_luminance)
                horizontal_gradient_count += 1
            previous_luminance = luminance
            sample_column = len(current_sample_row) - 1
            if previous_sample_row is not None and sample_column < len(previous_sample_row):
                vertical_gradient_total += abs(luminance - previous_sample_row[sample_column])
                vertical_gradient_count += 1
            red_total += red
            green_total += green
            blue_total += blue
            samples += 1
            is_dark = luminance < 0.08
            is_light = luminance > 0.94
            dark += int(is_dark)
            light += int(is_light)
            cell = cells[min(grid_size - 1, y * grid_size // height)][min(grid_size - 1, x * grid_size // width)]
            cell[0] += 1
            cell[1] += int(is_dark)
            cell[2] += int(is_light)
            grid_y = min(grid_size - 1, y * grid_size // height)
            grid_x = min(grid_size - 1, x * grid_size // width)
            spatial_sums[grid_y][grid_x] += luminance
            spatial_counts[grid_y][grid_x] += 1
            if zone_left <= x < zone_right and zone_top <= y < zone_bottom:
                zone_luminances.append(luminance)
        previous_sample_row = current_sample_row
    mean = sum(luminances) / samples
    variance = sum((value - mean) ** 2 for value in luminances) / samples
    zone_mean = sum(zone_luminances) / len(zone_luminances)
    zone_variance = sum((value - zone_mean) ** 2 for value in zone_luminances) / len(zone_luminances)
    contrasts = [
        (max(text_luminance, value) + 0.05) / (min(text_luminance, value) + 0.05)
        for value in zone_luminances
    ]
    contrasts.sort()
    percentile_index = max(0, int(len(contrasts) * 0.05) - 1)
    spatial_signature = [
        round(spatial_sums[row][column] / max(1, spatial_counts[row][column]), 5)
        for row in range(grid_size)
        for column in range(grid_size)
    ]
    horizontal_gradient = horizontal_gradient_total / max(1, horizontal_gradient_count)
    vertical_gradient = vertical_gradient_total / max(1, vertical_gradient_count)
    total_gradient = horizontal_gradient + vertical_gradient
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "width_px": width,
        "height_px": height,
        "mean_rgb": [round(red_total / samples), round(green_total / samples), round(blue_total / samples)],
        "mean_luminance": round(mean, 6),
        "luminance_stddev": round(math.sqrt(variance), 6),
        "near_black_ratio": round(dark / samples, 6),
        "near_white_ratio": round(light / samples, 6),
        "non_opaque_ratio": round(non_opaque / samples, 6),
        "largest_near_black_region_ratio": _largest_extreme_region(cells, 1),
        "largest_near_white_region_ratio": _largest_extreme_region(cells, 2),
        "copy_safe_mean_luminance": round(zone_mean, 6),
        "copy_safe_luminance_stddev": round(math.sqrt(zone_variance), 6),
        "copy_safe_contrast_p05": round(contrasts[percentile_index], 3),
        "spatial_luminance_signature": spatial_signature,
        "texture_gradient_energy": round(total_gradient / 2, 6),
        "texture_orientation_ratio": round(
            horizontal_gradient / total_gradient if total_gradient > 1e-9 else 0.5,
            6,
        ),
    }


def validate_background_family_assets(
    assets: list[tuple[str, Path]],
    *,
    surface_mode: str,
    copy_safe_zone: dict[str, Any],
    body_text_color: str,
    minimum_contrast_ratio: float = 4.5,
    maximum_copy_safe_stddev: float = 0.10,
    family_lineage: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    inspections: dict[str, dict[str, Any]] = {}
    if surface_mode not in {"light", "dark"}:
        errors.append("background family surface_mode must be light or dark")
    if not isinstance(family_lineage, dict):
        errors.append("background family requires generation lineage for every variant")
    for asset_id, path in assets:
        try:
            inspection = inspect_background_asset(path, copy_safe_zone, body_text_color)
        except (OSError, ValueError, ZeroDivisionError) as exc:
            errors.append(f"background family asset {asset_id} cannot be analyzed: {exc}")
            continue
        inspections[asset_id] = inspection
        if inspection["non_opaque_ratio"] > 0:
            errors.append(
                f"background family asset {asset_id} must be a final opaque PNG for deterministic contrast analysis"
            )
        mean = inspection["mean_luminance"]
        if surface_mode == "light" and mean < 0.50:
            errors.append(f"background family asset {asset_id} breaks light surface mode")
        if surface_mode == "dark" and mean > 0.46:
            errors.append(f"background family asset {asset_id} breaks dark surface mode")
        opposite_region = (
            inspection["largest_near_black_region_ratio"]
            if surface_mode == "light"
            else inspection["largest_near_white_region_ratio"]
        )
        if opposite_region > 0.20:
            errors.append(
                f"background family asset {asset_id} contains an opposite-tone block larger than 20%"
            )
        if inspection["copy_safe_luminance_stddev"] > maximum_copy_safe_stddev:
            errors.append(f"background family asset {asset_id} copy-safe zone is not near-solid")
        if inspection["copy_safe_contrast_p05"] < minimum_contrast_ratio:
            errors.append(
                f"background family asset {asset_id} copy-safe text contrast is below {minimum_contrast_ratio}:1"
            )
    if len(inspections) >= 2:
        means = [item["mean_luminance"] for item in inspections.values()]
        if max(means) - min(means) > 0.18:
            errors.append("background family luminance span exceeds 0.18; black/white chapter jumps are forbidden")
        zone_means = [item["copy_safe_mean_luminance"] for item in inspections.values()]
        if max(zone_means) - min(zone_means) > 0.14:
            errors.append("background family copy-safe surfaces do not share one tonal system")
        rgbs = [item["mean_rgb"] for item in inspections.values()]
        maximum_distance = max(
            math.dist(first, second) / (255 * math.sqrt(3))
            for first in rgbs
            for second in rgbs
        )
        if maximum_distance > 0.28:
            errors.append("background family average colors diverge beyond the allowed family range")
        texture_energies = [item["texture_gradient_energy"] for item in inspections.values()]
        if max(texture_energies) - min(texture_energies) > 0.055:
            errors.append("background family texture energy diverges; variants do not share one material grammar")
        orientations = [item["texture_orientation_ratio"] for item in inspections.values()]
        if max(texture_energies) > 0.015 and max(orientations) - min(orientations) > 0.28:
            errors.append("background family dominant texture orientation is inconsistent")
        signatures = [item["spatial_luminance_signature"] for item in inspections.values()]
        normalized: list[list[float]] = []
        for signature in signatures:
            mean_signature = sum(signature) / len(signature)
            deviation = math.sqrt(
                sum((value - mean_signature) ** 2 for value in signature) / len(signature)
            )
            normalized.append(
                [
                    (value - mean_signature) / max(0.025, deviation)
                    for value in signature
                ]
            )
        maximum_spatial_distance = max(
            math.sqrt(sum((x - y) ** 2 for x, y in zip(first, second)) / len(first))
            for first in normalized
            for second in normalized
        )
        if maximum_spatial_distance > 1.35:
            errors.append("background family spatial luminance grammar is structurally inconsistent")
    if isinstance(family_lineage, dict):
        asset_ids = [asset_id for asset_id, _ in assets]
        master_ids = {
            item.get("master_asset_id")
            for item in family_lineage.values()
            if isinstance(item, dict)
        }
        family_ids = {
            item.get("family_id")
            for item in family_lineage.values()
            if isinstance(item, dict)
        }
        routes = {
            item.get("generation_route")
            for item in family_lineage.values()
            if isinstance(item, dict)
        }
        prompt_hashes = {
            item.get("family_prompt_sha256")
            for item in family_lineage.values()
            if isinstance(item, dict)
        }
        if set(family_lineage) != set(asset_ids):
            errors.append("background family lineage must cover every analyzed variant exactly once")
        if len(master_ids) != 1 or next(iter(master_ids), None) not in asset_ids:
            errors.append("background family lineage must bind one analyzed master asset")
        if len(family_ids) != 1 or not next(iter(family_ids), None):
            errors.append("background family lineage must bind one family_id")
        if len(routes) != 1 or not next(iter(routes), None):
            errors.append("background family variants must share one generation_route")
        if (
            len(prompt_hashes) != 1
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(next(iter(prompt_hashes), "")))
        ):
            errors.append("background family variants must share one valid family_prompt_sha256")
        for asset_id in asset_ids:
            lineage = family_lineage.get(asset_id)
            if not isinstance(lineage, dict):
                continue
            variant_hash = lineage.get("variant_prompt_sha256")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(variant_hash or "")):
                errors.append(f"background family asset {asset_id} requires variant_prompt_sha256")
    return {"ok": not errors, "surface_mode": surface_mode, "inspections": inspections, "errors": errors}


def _robust_alpha_geometry(
    width: int,
    height: int,
    channels: int,
    rows: list[bytearray],
) -> dict[str, Any]:
    """Measure the largest connected alpha subject while ignoring detached artifacts.

    Row/column projections are insufficient here: four small but supported corner
    artifacts can make a tiny center subject appear tightly cropped.  Eight-connected
    components keep antialiased diagonal edges together while ensuring detached fly
    pixels cannot expand the approved subject bounds.
    """
    alpha_threshold = 32
    alpha_offset = channels - 1
    pixel_count = width * height
    mask = bytearray(pixel_count)
    substantive_pixels = 0
    for y, row in enumerate(rows):
        for x in range(width):
            if row[x * channels + alpha_offset] >= alpha_threshold:
                mask[y * width + x] = 1
                substantive_pixels += 1
    if not substantive_pixels:
        return {
            "alpha_bbox": None,
            "alpha_bbox_canvas_fill_ratio": None,
            "alpha_bbox_fill_ratio": None,
            "alpha_padding_ratio": None,
            "substantive_pixel_count": 0,
            "substantive_total_pixel_count": 0,
            "largest_component_ratio": None,
            "ignored_fly_pixel_count": 0,
            "touches_canvas_edge": False,
            "matte_color_ratio": None,
            "near_white_ratio": None,
            "dominant_color_ratio": None,
            "partial_pixel_count": 0,
            "near_white_halo_ratio": None,
            "near_black_halo_ratio": None,
            "partial_near_white_ratio": None,
            "partial_near_black_ratio": None,
            "partial_dominant_chroma_ratio": None,
            "partial_pixel_subject_ratio": None,
            "low_alpha_pixel_ratio": 0.0,
            "low_alpha_bbox_canvas_fill_ratio": None,
            "nonzero_alpha_touches_canvas_edge": False,
            "component_count": 0,
            "second_component_ratio": 0.0,
            "secondary_component_ratio": 0.0,
            "bbox_border_occupancy": None,
        }

    components: list[list[int]] = []
    for seed in range(pixel_count):
        if mask[seed] != 1:
            continue
        mask[seed] = 2
        stack = [seed]
        component: list[int] = []
        while stack:
            index = stack.pop()
            component.append(index)
            y, x = divmod(index, width)
            for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
                row_start = neighbor_y * width
                for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row_start + neighbor_x
                    if mask[neighbor] == 1:
                        mask[neighbor] = 2
                        stack.append(neighbor)
        components.append(component)
    components.sort(key=len, reverse=True)
    largest_component = components[0]

    left, top = width, height
    right = bottom = -1
    for index in largest_component:
        y, x = divmod(index, width)
        left = min(left, x)
        right = max(right, x)
        top = min(top, y)
        bottom = max(bottom, y)
    bbox_width = right - left + 1
    bbox_height = bottom - top + 1
    bbox_area = bbox_width * bbox_height
    selected_count = len(largest_component)
    matte_pixels = 0
    near_white = 0
    color_bins: dict[tuple[int, int, int], int] = {}
    for index in largest_component:
        y, x = divmod(index, width)
        row = rows[y]
        offset = x * channels
        if channels == 4:
            red, green, blue = row[offset : offset + 3]
        else:
            red = green = blue = row[offset]
        # Quantized dominant-colour evidence catches a flat opaque rectangle,
        # ellipse, or rounded color patch. White is recorded independently.
        color = (red // 16, green // 16, blue // 16)
        color_bins[color] = color_bins.get(color, 0) + 1
        if max(red, green, blue) - min(red, green, blue) <= 10 and max(red, green, blue) >= 238:
            near_white += 1
        if max(red, green, blue) - min(red, green, blue) <= 10:
            matte_pixels += 1

    # A thick neutral semi-transparent fringe is visible after compositing even
    # when it falls below the robust alpha threshold.  Measure it independently
    # across all non-zero partial-alpha pixels so white/black cutout residue cannot
    # hide behind the geometry filter.
    partial_pixels = 0
    near_white_halo = 0
    near_black_halo = 0
    low_alpha_pixels = 0
    low_alpha_left, low_alpha_top = width, height
    low_alpha_right = low_alpha_bottom = -1
    nonzero_alpha_touches_canvas_edge = False
    chroma_bins: dict[tuple[int, int, int], int] = {}
    for y, row in enumerate(rows):
        for x in range(width):
            offset = x * channels
            alpha = row[offset + alpha_offset]
            if alpha > 0 and (x == 0 or y == 0 or x == width - 1 or y == height - 1):
                nonzero_alpha_touches_canvas_edge = True
            if 0 < alpha < alpha_threshold:
                low_alpha_pixels += 1
                low_alpha_left = min(low_alpha_left, x)
                low_alpha_top = min(low_alpha_top, y)
                low_alpha_right = max(low_alpha_right, x)
                low_alpha_bottom = max(low_alpha_bottom, y)
            if not 0 < alpha < 250:
                continue
            partial_pixels += 1
            red, green, blue = row[offset : offset + 3]
            spread = max(red, green, blue) - min(red, green, blue)
            if spread <= 12 and min(red, green, blue) >= 238:
                near_white_halo += 1
            if spread <= 12 and max(red, green, blue) <= 18:
                near_black_halo += 1
            if spread >= 80 and max(red, green, blue) >= 100:
                color = (red // 16, green // 16, blue // 16)
                chroma_bins[color] = chroma_bins.get(color, 0) + 1
    dominant = max(color_bins.values()) if color_bins else 0
    dominant_chroma = max(chroma_bins.values()) if chroma_bins else 0
    low_alpha_bbox_canvas_fill_ratio = None
    if low_alpha_pixels:
        low_alpha_bbox_canvas_fill_ratio = round(
            ((low_alpha_right - low_alpha_left + 1) * (low_alpha_bottom - low_alpha_top + 1))
            / pixel_count,
            6,
        )
    ring = max(1, round(min(bbox_width, bbox_height) * 0.05))
    inner_width = max(0, bbox_width - 2 * ring)
    inner_height = max(0, bbox_height - 2 * ring)
    bbox_border_area = bbox_area - inner_width * inner_height
    bbox_border_pixels = 0
    for index in largest_component:
        y, x = divmod(index, width)
        if (
            x < left + ring
            or x > right - ring
            or y < top + ring
            or y > bottom - ring
        ):
            bbox_border_pixels += 1
    component_sizes = [len(component) for component in components]
    second_component_ratio = (
        component_sizes[1] / substantive_pixels if len(component_sizes) > 1 else 0.0
    )
    secondary_component_ratio = (substantive_pixels - selected_count) / substantive_pixels
    padding = {
        "left": round(left / width, 6),
        "top": round(top / height, 6),
        "right": round((width - right - 1) / width, 6),
        "bottom": round((height - bottom - 1) / height, 6),
    }
    return {
        "alpha_bbox": {"x": left, "y": top, "width": bbox_width, "height": bbox_height},
        "alpha_bbox_canvas_fill_ratio": round(bbox_area / (width * height), 6),
        "alpha_bbox_fill_ratio": round(selected_count / bbox_area, 6),
        "alpha_padding_ratio": padding,
        "substantive_pixel_count": selected_count,
        "substantive_total_pixel_count": substantive_pixels,
        "largest_component_ratio": round(selected_count / substantive_pixels, 6),
        "ignored_fly_pixel_count": substantive_pixels - selected_count,
        "touches_canvas_edge": left == 0 or top == 0 or right == width - 1 or bottom == height - 1,
        "matte_color_ratio": round(matte_pixels / selected_count, 6),
        "near_white_ratio": round(near_white / selected_count, 6),
        "dominant_color_ratio": round(dominant / selected_count, 6),
        "partial_pixel_count": partial_pixels,
        "near_white_halo_ratio": round(near_white_halo / selected_count, 6),
        "near_black_halo_ratio": round(near_black_halo / selected_count, 6),
        "partial_near_white_ratio": round(near_white_halo / partial_pixels, 6)
        if partial_pixels
        else 0.0,
        "partial_near_black_ratio": round(near_black_halo / partial_pixels, 6)
        if partial_pixels
        else 0.0,
        "partial_dominant_chroma_ratio": round(dominant_chroma / partial_pixels, 6)
        if partial_pixels
        else 0.0,
        "partial_pixel_subject_ratio": round(partial_pixels / selected_count, 6),
        "low_alpha_pixel_ratio": round(low_alpha_pixels / pixel_count, 6),
        "low_alpha_bbox_canvas_fill_ratio": low_alpha_bbox_canvas_fill_ratio,
        "nonzero_alpha_touches_canvas_edge": nonzero_alpha_touches_canvas_edge,
        "component_count": len(components),
        "second_component_ratio": round(second_component_ratio, 6),
        "secondary_component_ratio": round(secondary_component_ratio, 6),
        "bbox_border_occupancy": round(bbox_border_pixels / bbox_border_area, 6)
        if bbox_border_area
        else None,
    }


def inspect_png(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("asset must be a PNG file")
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        chunks.append((chunk_type, chunk_data))
        offset += 12 + length
        if chunk_type == b"IEND":
            break
    ihdr = next((value for kind, value in chunks if kind == b"IHDR"), None)
    if ihdr is None or len(ihdr) != 13:
        raise ValueError("PNG is missing a valid IHDR chunk")
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    has_alpha_channel = color_type in {4, 6} or any(kind == b"tRNS" for kind, _ in chunks)
    result: dict[str, Any] = {
        "format": "png",
        "width_px": width,
        "height_px": height,
        "aspect_ratio": round(width / height, 4),
        "bit_depth": bit_depth,
        "color_type": color_type,
        "has_alpha_channel": has_alpha_channel,
        "sha256": file_sha256(path),
        "transparent_pixel_ratio": None,
        "opaque_pixel_ratio": None,
        "has_transparent_pixels": False,
        "has_visible_pixels": True,
        "alpha_visible_bbox": None,
        "alpha_bbox_fill_ratio": None,
        "alpha_bbox_canvas_fill_ratio": None,
        "alpha_padding_ratio": None,
        "alpha_substantive_pixel_count": None,
        "alpha_substantive_total_pixel_count": None,
        "alpha_largest_component_ratio": None,
        "alpha_ignored_fly_pixel_count": None,
        "alpha_touches_canvas_edge": None,
        "alpha_matte_color_ratio": None,
        "alpha_near_white_ratio": None,
        "alpha_dominant_color_ratio": None,
        "alpha_partial_pixel_count": None,
        "alpha_near_white_halo_ratio": None,
        "alpha_near_black_halo_ratio": None,
        "alpha_partial_near_white_ratio": None,
        "alpha_partial_near_black_ratio": None,
        "alpha_partial_dominant_chroma_ratio": None,
        "alpha_partial_pixel_subject_ratio": None,
        "alpha_low_nonzero_pixel_ratio": None,
        "alpha_low_nonzero_bbox_canvas_fill_ratio": None,
        "alpha_nonzero_touches_canvas_edge": None,
        "alpha_component_count": None,
        "alpha_second_component_ratio": None,
        "alpha_secondary_component_ratio": None,
        "alpha_bbox_border_occupancy": None,
    }
    if not has_alpha_channel:
        return result
    if bit_depth != 8 or color_type != 6 or compression != 0 or filtering != 0 or interlace != 0:
        result["alpha_analysis"] = "channel-present-but-pixels-not-decoded"
        return result
    channels = 4
    stride = width * channels
    # Pillow is present in the supported runtime and delegates decompression and
    # PNG filtering to a well-tested deterministic decoder.  The strict IHDR
    # checks above still make the accepted carrier explicitly 8-bit RGBA.
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.load()
            if image.mode != "RGBA":
                raise ValueError("PNG RGBA decoder returned an unexpected pixel mode")
            rgba = image.tobytes()
        decoded_rows = [bytearray(rgba[index : index + stride]) for index in range(0, len(rgba), stride)]
    except ImportError:
        _, _, _, decoded_rows = _decoded_png_rows(path)
    transparent = 0
    visible = 0
    visible_left = width
    visible_top = height
    visible_right = -1
    visible_bottom = -1
    alpha_offset = channels - 1
    for y, decoded in enumerate(decoded_rows):
        for index in range(alpha_offset, stride, channels):
            alpha = decoded[index]
            x = (index - alpha_offset) // channels
            if alpha < 255:
                transparent += 1
            if alpha > 0:
                visible += 1
                visible_left = min(visible_left, x)
                visible_top = min(visible_top, y)
                visible_right = max(visible_right, x)
                visible_bottom = max(visible_bottom, y)
    pixels = width * height
    visible_bbox = None
    bbox_fill_ratio = None
    if visible:
        bbox_width = visible_right - visible_left + 1
        bbox_height = visible_bottom - visible_top + 1
        bbox_area = bbox_width * bbox_height
        visible_bbox = {
            "x": visible_left,
            "y": visible_top,
            "width": bbox_width,
            "height": bbox_height,
        }
        bbox_fill_ratio = round(visible / bbox_area, 6)
    robust = _robust_alpha_geometry(width, height, channels, decoded_rows)
    result.update(
        {
            "alpha_analysis": "decoded",
            "transparent_pixel_ratio": round(transparent / pixels, 6),
            "opaque_pixel_ratio": round((pixels - transparent) / pixels, 6),
            "has_transparent_pixels": transparent > 0,
            "has_visible_pixels": visible > 0,
            # The compatibility fields now use robust geometry.  The raw alpha
            # extrema remain available for forensic inspection but must never be
            # used to justify an oversized transparent canvas.
            "alpha_raw_visible_bbox": visible_bbox,
            "alpha_raw_bbox_fill_ratio": bbox_fill_ratio,
            "alpha_visible_bbox": robust["alpha_bbox"],
            "alpha_bbox_fill_ratio": robust["alpha_bbox_fill_ratio"],
            "alpha_bbox_canvas_fill_ratio": robust["alpha_bbox_canvas_fill_ratio"],
            "alpha_padding_ratio": robust["alpha_padding_ratio"],
            "alpha_substantive_pixel_count": robust["substantive_pixel_count"],
            "alpha_substantive_total_pixel_count": robust["substantive_total_pixel_count"],
            "alpha_largest_component_ratio": robust["largest_component_ratio"],
            "alpha_ignored_fly_pixel_count": robust["ignored_fly_pixel_count"],
            "alpha_touches_canvas_edge": robust["touches_canvas_edge"],
            "alpha_matte_color_ratio": robust["matte_color_ratio"],
            "alpha_near_white_ratio": robust["near_white_ratio"],
            "alpha_dominant_color_ratio": robust["dominant_color_ratio"],
            "alpha_partial_pixel_count": robust["partial_pixel_count"],
            "alpha_near_white_halo_ratio": robust["near_white_halo_ratio"],
            "alpha_near_black_halo_ratio": robust["near_black_halo_ratio"],
            "alpha_partial_near_white_ratio": robust["partial_near_white_ratio"],
            "alpha_partial_near_black_ratio": robust["partial_near_black_ratio"],
            "alpha_partial_dominant_chroma_ratio": robust["partial_dominant_chroma_ratio"],
            "alpha_partial_pixel_subject_ratio": robust["partial_pixel_subject_ratio"],
            "alpha_low_nonzero_pixel_ratio": robust["low_alpha_pixel_ratio"],
            "alpha_low_nonzero_bbox_canvas_fill_ratio": robust[
                "low_alpha_bbox_canvas_fill_ratio"
            ],
            "alpha_nonzero_touches_canvas_edge": robust[
                "nonzero_alpha_touches_canvas_edge"
            ],
            "alpha_component_count": robust["component_count"],
            "alpha_second_component_ratio": robust["second_component_ratio"],
            "alpha_secondary_component_ratio": robust["secondary_component_ratio"],
            "alpha_bbox_border_occupancy": robust["bbox_border_occupancy"],
        }
    )
    return result


def validate_micro_asset(path: Path, role: str) -> dict[str, Any]:
    errors: list[str] = []
    error_codes: set[str] = set()
    try:
        inspection = inspect_png(path)
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "path": str(path),
            "role": role,
            "errors": [str(exc)],
            "error_codes": ["micro.asset.unreadable"],
        }
    if role not in ROLE_ASPECT_RATIOS:
        error_codes.add("micro.asset.unknown_role")
        errors.append(f"unknown micro-visual role: {role}")
    else:
        minimum, maximum = ROLE_ASPECT_RATIOS[role]
        ratio = inspection["aspect_ratio"]
        if not minimum <= ratio <= maximum:
            errors.append(
                f"{role} aspect ratio must be between {minimum} and {maximum}; found {ratio}"
            )
    if inspection["width_px"] < 256 or inspection["height_px"] < 128:
        error_codes.add("micro.asset.minimum_dimensions")
        errors.append("micro asset must be at least 256 px wide and 128 px high")
    if not inspection["has_alpha_channel"]:
        error_codes.add("micro.asset.missing_alpha_channel")
        errors.append("micro asset requires a real PNG alpha channel")
    if inspection.get("bit_depth") != 8 or inspection.get("color_type") != 6:
        error_codes.add("micro.asset.requires_rgba8")
        errors.append("micro asset requires deterministically decodable 8-bit RGBA PNG pixels")
    if inspection.get("alpha_analysis") != "decoded":
        error_codes.add("micro.asset.alpha_not_decodable")
        errors.append("micro asset alpha pixels must be deterministically decodable")
    elif not inspection["has_transparent_pixels"]:
        error_codes.add("micro.asset.no_transparent_pixels")
        errors.append("micro asset alpha channel contains no transparent pixels")
    elif not inspection["has_visible_pixels"]:
        error_codes.add("micro.asset.fully_transparent")
        errors.append("micro asset is fully transparent")
    transparent_ratio = inspection.get("transparent_pixel_ratio")
    if isinstance(transparent_ratio, float) and transparent_ratio < 0.01:
        error_codes.add("micro.asset.insufficient_transparency")
        errors.append("micro asset has less than 1% transparent pixels; open edges are not credible")
    bbox_fill_ratio = inspection.get("alpha_bbox_fill_ratio")
    if isinstance(bbox_fill_ratio, float) and bbox_fill_ratio > 0.94:
        error_codes.add("micro.asset.rectangular_alpha_tile")
        errors.append(
            "micro asset alpha silhouette fills more than 94% of its visible bounding box; "
            "rectangular tiles and transparent-border cards are forbidden"
        )
    bbox = inspection.get("alpha_visible_bbox")
    if isinstance(bbox, dict):
        minimum_width, minimum_height = ROLE_MINIMUM_CANVAS_COVERAGE.get(role, (0.62, 0.54))
        width_coverage = bbox["width"] / inspection["width_px"]
        height_coverage = bbox["height"] / inspection["height_px"]
        if width_coverage < minimum_width or height_coverage < minimum_height:
            error_codes.add("micro.asset.oversized_transparent_canvas")
            errors.append(
                "micro asset subject is not tightly cropped; transparent layout whitespace is forbidden "
                f"(coverage {width_coverage:.3f}×{height_coverage:.3f})"
            )
    elif inspection.get("alpha_analysis") == "decoded" and inspection.get("has_visible_pixels"):
        error_codes.add("micro.asset.insubstantial_alpha")
        errors.append("micro asset has no substantial alpha silhouette after fly-pixel filtering")
    if inspection.get("alpha_touches_canvas_edge") is True:
        error_codes.add("micro.asset.clipped_subject")
        errors.append("micro asset substantive alpha touches a canvas edge; subject may be clipped")
    if inspection.get("alpha_nonzero_touches_canvas_edge") is True:
        error_codes.add("micro.asset.alpha_residue_touches_canvas_edge")
        errors.append(
            "micro asset contains non-zero Alpha on the outer canvas edge; clipped subject or "
            "low-Alpha background residue is forbidden"
        )
    low_alpha_ratio = inspection.get("alpha_low_nonzero_pixel_ratio")
    low_alpha_bbox_ratio = inspection.get("alpha_low_nonzero_bbox_canvas_fill_ratio")
    if (
        isinstance(low_alpha_ratio, float)
        and low_alpha_ratio >= 0.08
        and isinstance(low_alpha_bbox_ratio, float)
        and low_alpha_bbox_ratio >= 0.70
    ):
        error_codes.add("micro.asset.low_alpha_background_plane")
        errors.append(
            "micro asset contains a canvas-scale low-Alpha background plane; transparent "
            "pixels must belong only to the subject edge or an intentional local effect"
        )
    second_component_ratio = inspection.get("alpha_second_component_ratio")
    secondary_component_ratio = inspection.get("alpha_secondary_component_ratio")
    if (
        isinstance(second_component_ratio, float)
        and second_component_ratio >= 0.10
    ) or (
        isinstance(secondary_component_ratio, float)
        and secondary_component_ratio >= 0.25
    ):
        error_codes.add("micro.asset.detached_debris")
        errors.append(
            "micro asset contains a detached substantial component; retain one coherent subject "
            "with only small nearby open strokes"
        )
    dominant_ratio = inspection.get("alpha_dominant_color_ratio")
    near_white_ratio = inspection.get("alpha_near_white_ratio")
    if (
        isinstance(bbox_fill_ratio, float)
        and bbox_fill_ratio >= 0.72
        and isinstance(dominant_ratio, float)
        and dominant_ratio >= 0.88
    ):
        error_codes.add("micro.asset.solid_color_matte")
        errors.append("micro asset contains a near-solid rectangular or rounded matte; use a subject-only cut-out")
    if (
        isinstance(bbox_fill_ratio, float)
        and bbox_fill_ratio >= 0.65
        and isinstance(near_white_ratio, float)
        and near_white_ratio >= 0.80
    ):
        error_codes.add("micro.asset.white_matte")
        errors.append("micro asset contains a white matte or rounded white card; background must be removed")
    bbox_border_occupancy = inspection.get("alpha_bbox_border_occupancy")
    if (
        isinstance(bbox_fill_ratio, float)
        and bbox_fill_ratio >= 0.82
        and isinstance(bbox_border_occupancy, float)
        and bbox_border_occupancy >= 0.55
    ):
        error_codes.add("micro.asset.background_plane_silhouette")
        errors.append(
            "micro asset silhouette behaves like an irregular or textured background plane; "
            "use a subject-only cut-out"
        )
    white_halo_ratio = inspection.get("alpha_partial_near_white_ratio")
    black_halo_ratio = inspection.get("alpha_partial_near_black_ratio")
    colored_halo_ratio = inspection.get("alpha_partial_dominant_chroma_ratio")
    partial_subject_ratio = inspection.get("alpha_partial_pixel_subject_ratio")
    meaningful_partial_edge = (
        isinstance(partial_subject_ratio, float) and partial_subject_ratio >= 0.02
    )
    if meaningful_partial_edge and isinstance(white_halo_ratio, float) and white_halo_ratio >= 0.60:
        error_codes.add("micro.asset.white_halo")
        errors.append("micro asset contains a visible semi-transparent white edge halo")
    if meaningful_partial_edge and isinstance(black_halo_ratio, float) and black_halo_ratio >= 0.60:
        error_codes.add("micro.asset.black_halo")
        errors.append("micro asset contains a visible semi-transparent black edge halo")
    if meaningful_partial_edge and isinstance(colored_halo_ratio, float) and colored_halo_ratio >= 0.60:
        error_codes.add("micro.asset.colored_halo")
        errors.append(
            "micro asset contains a dominant semi-transparent colored edge halo; remove key-color spill"
        )
    return {
        "ok": not errors,
        "path": str(path),
        "role": role,
        "inspection": inspection,
        "errors": errors,
        "error_codes": sorted(error_codes),
    }
