#!/usr/bin/env python3
"""Create a deterministic true-alpha micro cutout from a controlled PNG source.

Each real article component explicitly selects one of two raw-source routes:
``--require-native-alpha`` verifies provider-original transparency without
inferring a background, while ``--key-color`` accepts only a deliberately
uniform, safely removable chroma-key background.  Either route may be the first
article-specific attempt.  Both converge on the same strict final RGBA8 gate;
arbitrary photographs and complex scenes fail instead of being force-masked.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import tempfile
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median_low
from typing import Any

from provider_acquisition_authority import (
    ACQUISITION_KIND,
    LiveAuthorityCallback,
    validate_provider_acquisition_bundle,
)


ROLE_TARGET_RATIOS = {
    "floating-spot": 1.0,
    "section-transition": 4.0,
    "inline-explainer": 4.0 / 3.0,
    "closing-motif": 1.0,
}
DEFAULT_PROBE_COLORS = ("#000000", "#FFFFFF", "#F4F2EC", "#111111")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
ROUTE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{1,127}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLOT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_ACQUISITION_AGE = timedelta(days=7)
MAX_ACQUISITION_FUTURE_SKEW = timedelta(minutes=5)
MAX_ACQUISITION_COMPLETION_LAG = timedelta(hours=1)
NATIVE_FAILURE_CODES = {
    "cutout.source.native_alpha_required",
    "cutout.source.invalid_native_rgba",
}


class CutoutPreparationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return _sha256_bytes(encoded)


def _parse_color(value: str) -> tuple[int, int, int]:
    if not HEX_COLOR.fullmatch(value):
        raise CutoutPreparationError("cutout.config.invalid_color", f"invalid #RRGGBB color: {value}")
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _pixel_sha256(image: Any) -> str:
    header = f"{image.mode}:{image.width}x{image.height}:".encode("ascii")
    return _sha256_bytes(header + image.tobytes())


def _has_symlink_component(path: Path) -> bool:
    """Reject lexical user symlinks before any resolve or file creation."""

    absolute = path.expanduser().absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def _safe_source(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    if _has_symlink_component(absolute):
        raise CutoutPreparationError(
            "cutout.path.symlink_forbidden",
            f"source path contains a symbolic link: {absolute}",
        )
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as exc:
        raise CutoutPreparationError("cutout.source.unreadable", f"source is unavailable: {exc}") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise CutoutPreparationError("cutout.source.unreadable", "source must be a regular non-symlink file")
    return resolved


def _safe_new_path(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    if _has_symlink_component(absolute.parent):
        raise CutoutPreparationError(
            "cutout.path.symlink_forbidden",
            f"output path parent contains a symbolic link: {absolute.parent}",
        )
    if os.path.lexists(absolute):
        raise CutoutPreparationError(
            "cutout.output.create_once", f"refusing to overwrite an existing path: {absolute}"
        )
    if not absolute.parent.is_dir():
        raise CutoutPreparationError(
            "cutout.path.parent_unavailable",
            "output/report parent must already exist as a real directory",
        )
    try:
        resolved_parent = absolute.parent.resolve(strict=True)
    except OSError as exc:
        raise CutoutPreparationError(
            "cutout.path.parent_unavailable", f"output parent is unavailable: {exc}"
        ) from exc
    candidate = resolved_parent / absolute.name
    if os.path.lexists(candidate):
        raise CutoutPreparationError(
            "cutout.output.create_once", f"refusing to overwrite an existing path: {candidate}"
        )
    return candidate


def _relative_to_report(path: Path, report_path: Path) -> str:
    return Path(os.path.relpath(path, report_path.parent)).as_posix()


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _is_iso_datetime(value: Any) -> bool:
    return _parse_iso_datetime(value) is not None


def validate_acquisition_report(
    report_path: Path,
    source_path: Path,
    *,
    article_id: str,
    asset_slot_id: str,
    prompt_sha256: str,
    generation_route: str,
    expected_mode: str,
    key_color: str | None,
    enforce_current_freshness: bool = True,
    live_authority: LiveAuthorityCallback | None = None,
    portable_trust_store: Path | None = None,
    require_authority: bool = True,
) -> dict[str, Any]:
    """Validate provider/download provenance and the selected real-asset route."""

    errors: list[str] = []
    if report_path.is_symlink():
        return {"ok": False, "errors": ["acquisition report cannot be a symlink"]}
    try:
        candidate = report_path.resolve(strict=True)
        if not candidate.is_file():
            raise OSError("not a regular file")
        report = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"acquisition report is unavailable: {exc}"]}
    if not isinstance(report, dict):
        return {"ok": False, "errors": ["acquisition report must be a JSON object"]}
    if report.get("schema_version") != 2 or report.get("kind") != ACQUISITION_KIND:
        errors.append("acquisition report schema/kind is invalid")
    expected = {
        "article_id": article_id,
        "asset_slot_id": asset_slot_id,
        "prompt_sha256": prompt_sha256,
        "generation_route": generation_route,
    }
    for field, value in expected.items():
        if report.get(field) != value:
            errors.append(f"acquisition report {field} does not match the cutout request")
    trace = report.get("host_trace") if isinstance(report.get("host_trace"), dict) else {}
    for field in ("provider", "session_id", "download_id"):
        if not isinstance(trace.get(field), str) or not trace.get(field):
            errors.append(f"acquisition host_trace.{field} is required")
    completed_at = _parse_iso_datetime(trace.get("completed_at"))
    if completed_at is None:
        errors.append("acquisition host_trace.completed_at must be a timezone-aware ISO timestamp")
    elif enforce_current_freshness:
        now = datetime.now(timezone.utc)
        if completed_at > now + MAX_ACQUISITION_FUTURE_SKEW:
            errors.append("acquisition host_trace.completed_at is implausibly in the future")
        if completed_at < now - MAX_ACQUISITION_AGE:
            errors.append("acquisition report is stale and must be reacquired in the current workflow run")

    attempts_raw = report.get("attempts")
    attempts = (
        [item for item in attempts_raw if isinstance(item, dict)]
        if isinstance(attempts_raw, list)
        else []
    )
    valid_counts = {1} if expected_mode == "native-alpha" else {1, 2}
    if len(attempts) not in valid_counts or len(attempts) != len(attempts_raw or []):
        expected_label = "1" if expected_mode == "native-alpha" else "1 or 2"
        errors.append(
            f"acquisition attempt ledger must contain exactly {expected_label} ordered attempts"
        )
    request_ids: set[str] = set()
    accepted: dict[str, Any] | None = None
    downloaded_times: list[datetime | None] = []
    for index, attempt in enumerate(attempts, 1):
        if attempt.get("attempt_index") != index:
            errors.append("acquisition attempts must use contiguous one-based attempt_index values")
        request_id = attempt.get("provider_request_id")
        if not isinstance(request_id, str) or not request_id:
            errors.append(f"acquisition attempt {index} requires provider_request_id")
        elif request_id in request_ids:
            errors.append("acquisition attempts must bind distinct provider requests")
        else:
            request_ids.add(request_id)
        downloaded_at = _parse_iso_datetime(attempt.get("downloaded_at"))
        downloaded_times.append(downloaded_at)
        if downloaded_at is None:
            errors.append(
                f"acquisition attempt {index} downloaded_at must be a timezone-aware ISO timestamp"
            )
        if not SHA256.fullmatch(str(attempt.get("source_file_sha256", ""))):
            errors.append(f"acquisition attempt {index} requires source_file_sha256")
        if not SHA256.fullmatch(str(attempt.get("prompt_sha256", ""))):
            errors.append(f"acquisition attempt {index} requires its own prompt_sha256")
        if attempt.get("outcome") == "accepted":
            accepted = attempt

    aware_downloads = [value for value in downloaded_times if value is not None]
    if len(aware_downloads) == len(downloaded_times) and aware_downloads:
        if any(current <= previous for previous, current in zip(aware_downloads, aware_downloads[1:])):
            errors.append("acquisition attempt downloaded_at values must be strictly increasing")
        if completed_at is not None:
            if aware_downloads[-1] > completed_at:
                errors.append("acquisition attempts must complete no later than host_trace.completed_at")
            elif completed_at - aware_downloads[-1] > MAX_ACQUISITION_COMPLETION_LAG:
                errors.append("acquisition completion timestamp is too far after the accepted download")

    current_source_sha = _sha256_file(source_path)
    if expected_mode == "native-alpha":
        if attempts:
            first = attempts[0]
            if first.get("mode") != "native-alpha" or first.get("outcome") != "accepted":
                errors.append("native-alpha route requires one accepted native attempt")
    else:
        if len(attempts) == 1:
            first = attempts[0]
            if first.get("mode") != "controlled-key" or first.get("outcome") != "accepted":
                errors.append(
                    "single-attempt controlled-key route requires one accepted controlled-key source"
                )
            if first.get("key_color") != key_color:
                errors.append(
                    "controlled-key acquisition key_color does not match processor configuration"
                )
        elif len(attempts) >= 2:
            first = attempts[0]
            if first.get("mode") != "native-alpha" or first.get("outcome") != "rejected":
                errors.append(
                    "two-attempt controlled-key route requires a rejected native-alpha attempt first"
                )
            if first.get("failure_code") not in NATIVE_FAILURE_CODES:
                errors.append(
                    "two-attempt controlled-key route requires a real native Alpha/pixel gate failure code"
                )
            second = attempts[1]
            if second.get("mode") != "controlled-key" or second.get("outcome") != "accepted":
                errors.append("the second and final attempt must be an accepted controlled-key source")
            if second.get("key_color") != key_color:
                errors.append("controlled-key acquisition key_color does not match processor configuration")
            if first.get("source_file_sha256") == second.get("source_file_sha256"):
                errors.append(
                    "controlled-key fallback must bind a newly generated source, not relabel the failed native attempt"
                )
    if accepted is None or accepted.get("source_file_sha256") != current_source_sha:
        errors.append("accepted acquisition attempt does not bind the current original PNG bytes")
    if accepted is not None and accepted.get("prompt_sha256") != prompt_sha256:
        errors.append(
            "cutout prompt_sha256 must equal the accepted acquisition attempt prompt"
        )
    authority = validate_provider_acquisition_bundle(
        candidate,
        source_path,
        article_id=article_id,
        asset_slot_id=asset_slot_id,
        prompt_sha256=prompt_sha256,
        generation_route=generation_route,
        attempts=attempts,
        live_authority=live_authority,
        portable_trust_store=portable_trust_store,
        require_authority=require_authority,
    )
    errors.extend(authority["errors"])
    return {
        "ok": not errors,
        "errors": errors,
        "report": report,
        "report_path": candidate,
        "report_sha256": _sha256_file(candidate),
        "attempt_count": len(attempts),
        "accepted_attempt_index": accepted.get("attempt_index") if accepted else None,
        "authority": authority,
    }


def _distance_sq(first: tuple[int, int, int], second: tuple[int, int, int]) -> int:
    return sum((left - right) ** 2 for left, right in zip(first, second))


def _distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return math.sqrt(_distance_sq(first, second))


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _largest_ring_cluster(
    non_background: set[tuple[int, int]], width: int, height: int, ring: int
) -> int:
    largest = 0
    remaining = set(non_background)
    while remaining:
        seed = remaining.pop()
        stack = [seed]
        size = 0
        while stack:
            x, y = stack.pop()
            size += 1
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    if not (nx < ring or nx >= width - ring or ny < ring or ny >= height - ring):
                        continue
                    neighbor = (nx, ny)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
        largest = max(largest, size)
    return largest


def _background_assessment(
    image: Any,
    *,
    requested_key: str | None,
    border_ring_ratio: float,
    border_p95_limit_rgb: float,
    soft_distance_rgb: float,
    minimum_border_background_ratio: float,
) -> tuple[tuple[int, int, int], dict[str, Any]]:
    width, height = image.size
    pixels = image.load()
    ring = max(4, round(min(width, height) * border_ring_ratio))
    samples: list[tuple[int, int, int]] = []
    coordinates: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if x < ring or x >= width - ring or y < ring or y >= height - ring:
                samples.append(pixels[x, y])
                coordinates.append((x, y))
    estimated = tuple(int(median_low([pixel[channel] for pixel in samples])) for channel in range(3))
    chroma = max(estimated) - min(estimated)
    if chroma < 120 or max(estimated) < 180 or min(estimated) > 100:
        raise CutoutPreparationError(
            "cutout.source.key_not_chromatic",
            "opaque source border is not a controlled high-chroma key background",
        )
    expected = _parse_color(requested_key) if requested_key else estimated
    expected_distance = _distance(estimated, expected)
    if requested_key and expected_distance > 40:
        raise CutoutPreparationError(
            "cutout.source.key_mismatch",
            "observed border color does not match the requested key color",
        )
    distances = [_distance(pixel, estimated) for pixel in samples]
    background_flags = [distance <= soft_distance_rgb for distance in distances]
    background_ratio = sum(background_flags) / len(background_flags)
    p95 = _percentile(distances, 0.95)
    non_background = {
        coordinate
        for coordinate, is_background in zip(coordinates, background_flags)
        if not is_background
    }
    largest_cluster = _largest_ring_cluster(non_background, width, height, ring)
    outer_edge = [
        pixels[x, y]
        for y in range(height)
        for x in range(width)
        if x == 0 or y == 0 or x == width - 1 or y == height - 1
    ]
    outer_background_ratio = sum(
        _distance(pixel, estimated) <= soft_distance_rgb for pixel in outer_edge
    ) / len(outer_edge)
    if (
        p95 > border_p95_limit_rgb
        or background_ratio < minimum_border_background_ratio
        or outer_background_ratio < 0.995
        or largest_cluster > max(8, round(len(samples) * 0.001))
    ):
        raise CutoutPreparationError(
            "cutout.source.background_not_uniform",
            "source border is non-uniform or the subject touches the key-background safety ring; regenerate",
        )
    return estimated, {
        "ring_px": ring,
        "estimated_key_rgb": list(estimated),
        "requested_key": requested_key,
        "requested_key_distance_rgb": round(expected_distance, 6),
        "border_p95_distance_rgb": round(p95, 6),
        "border_background_ratio": round(background_ratio, 6),
        "outer_edge_background_ratio": round(outer_background_ratio, 6),
        "largest_non_background_ring_cluster_px": largest_cluster,
        "source_background_removable": True,
    }


def _connected_key_mask(image: Any, key: tuple[int, int, int], soft_distance_rgb: float) -> bytearray:
    width, height = image.size
    pixels = image.load()
    limit = soft_distance_rgb * soft_distance_rgb
    mask = bytearray(width * height)
    queue: deque[int] = deque()

    def seed(x: int, y: int) -> None:
        index = y * width + x
        if mask[index] == 0 and _distance_sq(pixels[x, y], key) <= limit:
            mask[index] = 1
            queue.append(index)

    for x in range(width):
        seed(x, 0)
        seed(x, height - 1)
    for y in range(height):
        seed(0, y)
        seed(width - 1, y)
    while queue:
        index = queue.popleft()
        y, x = divmod(index, width)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            neighbor = ny * width + nx
            if mask[neighbor] or _distance_sq(pixels[nx, ny], key) > limit:
                continue
            mask[neighbor] = 1
            queue.append(neighbor)
    return mask


def _matte_key_background(
    image: Any,
    key: tuple[int, int, int],
    *,
    sure_distance_rgb: float,
    soft_distance_rgb: float,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    from PIL import Image

    width, height = image.size
    pixels = image.load()
    connected = _connected_key_mask(image, key, soft_distance_rgb)
    connected_count = sum(connected)
    if connected_count / (width * height) < 0.08:
        raise CutoutPreparationError(
            "cutout.source.background_connectivity_low",
            "too little border-connected key background remains; regenerate with an isolated subject",
        )
    alpha_values = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if not connected[index]:
                alpha_values[index] = 255
                continue
            distance = _distance(pixels[x, y], key)
            if distance <= sure_distance_rgb:
                alpha = 0
            else:
                position = min(
                    1.0,
                    (distance - sure_distance_rgb) / (soft_distance_rgb - sure_distance_rgb),
                )
                alpha = round(255 * position * position * (3.0 - 2.0 * position))
            alpha_values[index] = 0 if alpha < 16 else max(0, min(255, alpha))

    output = bytearray(width * height * 4)
    partial_pixels = 0
    key_spill_evaluated_pixels = 0
    key_spill_pixels = 0
    unresolved_partial_pixels = 0
    substantive_pixels = 0
    for y in range(height):
        for x in range(width):
            index = y * width + x
            red, green, blue = pixels[x, y]
            alpha = alpha_values[index]
            output_index = index * 4
            if alpha == 0:
                output[output_index : output_index + 4] = b"\x00\x00\x00\x00"
                continue
            if alpha < 255:
                best_foreground: tuple[int, int, int] | None = None
                best_distance = -1.0
                for radius in range(1, 9):
                    for ny in range(max(0, y - radius), min(height, y + radius + 1)):
                        for nx in range(max(0, x - radius), min(width, x + radius + 1)):
                            neighbor = ny * width + nx
                            if alpha_values[neighbor] != 255:
                                continue
                            candidate = pixels[nx, ny]
                            distance = _distance(candidate, key)
                            if distance > best_distance:
                                best_distance = distance
                                best_foreground = candidate
                    if best_distance >= soft_distance_rgb + 30:
                        break
                if best_foreground is None or best_distance < soft_distance_rgb + 10:
                    unresolved_partial_pixels += 1
                else:
                    numerator = sum(
                        (channel - background) * (foreground - background)
                        for channel, background, foreground in zip(
                            (red, green, blue), key, best_foreground
                        )
                    )
                    denominator = sum(
                        (foreground - background) ** 2
                        for foreground, background in zip(best_foreground, key)
                    )
                    opacity = max(0.0, min(1.0, numerator / denominator)) if denominator else 0.0
                    alpha = round(opacity * 255)
                    if alpha < 16:
                        alpha = 0
                    else:
                        red, green, blue = best_foreground
                if alpha == 0:
                    output[output_index : output_index + 4] = b"\x00\x00\x00\x00"
                    continue
                partial_pixels += 1
                if alpha >= 32:
                    key_spill_evaluated_pixels += 1
                    if _distance((red, green, blue), key) <= 70:
                        key_spill_pixels += 1
            if alpha >= 32:
                substantive_pixels += 1
            output[output_index : output_index + 4] = bytes((red, green, blue, alpha))
    if substantive_pixels == 0:
        raise CutoutPreparationError("cutout.mask.empty", "background removal produced no subject")
    partial_subject_ratio = partial_pixels / substantive_pixels
    unresolved_ratio = (
        unresolved_partial_pixels / partial_pixels if partial_pixels else 0.0
    )
    spill_ratio = (
        key_spill_pixels / key_spill_evaluated_pixels if key_spill_evaluated_pixels else 0.0
    )
    if partial_subject_ratio > 0.30 or unresolved_ratio > 0.02:
        raise CutoutPreparationError(
            "cutout.source.complex_transparency",
            "source requires complex transparency or cannot be safely separated from the key background",
        )
    if spill_ratio > 0.02:
        raise CutoutPreparationError(
            "cutout.edge.key_spill",
            "key-color spill remains on the recovered subject edge "
            f"({spill_ratio:.4f}); regenerate with a different key",
        )
    return (
        Image.frombytes("RGBA", (width, height), bytes(output)),
        {
            "connected_background_pixel_ratio": round(connected_count / (width * height), 6),
            "foreground_substantive_pixel_count": substantive_pixels,
        },
        {
            "partial_pixel_count": partial_pixels,
            "partial_pixel_subject_ratio": round(partial_subject_ratio, 6),
            "key_spill_pixel_count": key_spill_pixels,
            "key_spill_evaluated_pixel_count": key_spill_evaluated_pixels,
            "key_spill_ratio": round(spill_ratio, 6),
            "unresolved_partial_pixel_count": unresolved_partial_pixels,
            "unresolved_partial_ratio": round(unresolved_ratio, 6),
            "decontamination": "nearest-foreground-inverse-composite-v1",
        },
    )


def _alpha_components(image: Any, threshold: int = 32) -> list[list[int]]:
    width, height = image.size
    alpha = image.getchannel("A").tobytes()
    mask = bytearray(1 if value >= threshold else 0 for value in alpha)
    components: list[list[int]] = []
    for seed in range(width * height):
        if mask[seed] != 1:
            continue
        mask[seed] = 2
        stack = [seed]
        component: list[int] = []
        while stack:
            index = stack.pop()
            component.append(index)
            y, x = divmod(index, width)
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if mask[neighbor] == 1:
                        mask[neighbor] = 2
                        stack.append(neighbor)
        components.append(component)
    components.sort(key=len, reverse=True)
    return components


def _clean_and_crop(image: Any, role: str, safety_margin_ratio: float) -> tuple[Any, dict[str, Any]]:
    from PIL import Image

    components = _alpha_components(image)
    if not components:
        raise CutoutPreparationError("cutout.mask.empty", "cutout contains no substantive Alpha subject")
    total = sum(len(component) for component in components)
    largest = len(components[0])
    second_ratio = len(components[1]) / total if len(components) > 1 else 0.0
    secondary_ratio = (total - largest) / total
    if second_ratio >= 0.10 or secondary_ratio >= 0.25:
        raise CutoutPreparationError(
            "cutout.mask.detached_debris",
            "cutout contains a detached substantial component; regenerate one coherent subject",
        )
    keep_minimum = max(8, round(largest * 0.002))
    retained = [component for component in components if len(component) >= keep_minimum]
    retained_indices = {index for component in retained for index in component}
    width, height = image.size
    rgba = bytearray(image.tobytes())
    for index in range(width * height):
        alpha = rgba[index * 4 + 3]
        if alpha >= 32 and index not in retained_indices:
            rgba[index * 4 : index * 4 + 4] = b"\x00\x00\x00\x00"
        elif alpha == 0:
            rgba[index * 4 : index * 4 + 3] = b"\x00\x00\x00"
    image = Image.frombytes("RGBA", (width, height), bytes(rgba))
    xs: list[int] = []
    ys: list[int] = []
    for index in retained_indices:
        y, x = divmod(index, width)
        xs.append(x)
        ys.append(y)
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    subject_width = right - left + 1
    subject_height = bottom - top + 1
    safety = max(4, round(max(subject_width, subject_height) * safety_margin_ratio))
    crop_left = max(0, left - safety)
    crop_top = max(0, top - safety)
    crop_right = min(width, right + safety + 1)
    crop_bottom = min(height, bottom + safety + 1)
    subject = image.crop((crop_left, crop_top, crop_right, crop_bottom))
    target_ratio = ROLE_TARGET_RATIOS[role]
    canvas_width, canvas_height = subject.size
    if canvas_width / canvas_height < target_ratio:
        canvas_width = math.ceil(canvas_height * target_ratio)
    else:
        canvas_height = math.ceil(canvas_width / target_ratio)
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    offset = ((canvas_width - subject.width) // 2, (canvas_height - subject.height) // 2)
    canvas.alpha_composite(subject, offset)
    sanitized = bytearray(canvas.tobytes())
    for index in range(canvas_width * canvas_height):
        if sanitized[index * 4 + 3] == 0:
            sanitized[index * 4 : index * 4 + 3] = b"\x00\x00\x00"
    canvas = Image.frombytes("RGBA", canvas.size, bytes(sanitized))
    return canvas, {
        "source_component_count": len(components),
        "retained_component_count": len(retained),
        "largest_component_ratio": round(largest / total, 6),
        "second_component_ratio": round(second_ratio, 6),
        "secondary_component_ratio": round(secondary_ratio, 6),
        "removed_fly_pixel_count": total - sum(len(component) for component in retained),
        "substantive_bbox": {
            "x": left,
            "y": top,
            "width": subject_width,
            "height": subject_height,
        },
        "safety_margin_px": safety,
        "target_aspect_ratio": round(target_ratio, 6),
        "output_canvas_px": {"width": canvas_width, "height": canvas_height},
    }


def _png_bytes(image: Any) -> bytes:
    destination = io.BytesIO()
    image.save(destination, format="PNG", optimize=False, compress_level=9)
    return destination.getvalue()


def _composite_probes(image: Any, colors: list[str]) -> list[dict[str, Any]]:
    from PIL import Image

    probes: list[dict[str, Any]] = []
    for color in colors:
        rgb = _parse_color(color)
        background = Image.new("RGBA", image.size, (*rgb, 255))
        composite = Image.alpha_composite(background, image).convert("RGB")
        probes.append({"background": color.upper(), "pixel_sha256": _pixel_sha256(composite)})
    return probes


def _validate_final_png(png: bytes, role: str, parent: Path) -> dict[str, Any]:
    from asset_quality import validate_micro_asset

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=parent, suffix=".png", delete=False) as handle:
            handle.write(png)
            temporary = Path(handle.name)
        validation = validate_micro_asset(temporary, role)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    if not validation["ok"]:
        raise CutoutPreparationError(
            "cutout.output.quality_failed", "; ".join(validation.get("errors", []))
        )
    return validation


def _validate_native_source_safety(source: Path) -> dict[str, Any]:
    """Reject unsafe Alpha before crop without applying final role geometry yet."""

    from asset_quality import validate_native_rgba_source

    return validate_native_rgba_source(source)


def _prepare_micro_cutout(
    source_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    role: str,
    article_id: str,
    asset_slot_id: str,
    prompt_sha256: str,
    generation_route: str,
    acquisition_report_path: Path | None = None,
    key_color: str | None = None,
    require_native_alpha: bool = False,
    probe_colors: list[str] | None = None,
    live_authority: LiveAuthorityCallback | None = None,
    portable_trust_store: Path | None = None,
    migration_probe_authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare one cutout after formal or migration-only authority validation.

    ``migration_probe_authority`` is private to the locked migration processor.
    The public ``prepare_micro_cutout`` wrapper below never accepts it, so the
    formal article path continues to require a provider acquisition report.
    """

    from PIL import Image, __version__ as pillow_version

    if role not in ROLE_TARGET_RATIOS:
        raise CutoutPreparationError("cutout.config.unknown_role", f"unknown micro role: {role}")
    if not SLUG.fullmatch(article_id):
        raise CutoutPreparationError(
            "cutout.config.invalid_article_id", "article_id must be a lowercase hyphenated slug"
        )
    if not SLOT_ID.fullmatch(asset_slot_id):
        raise CutoutPreparationError(
            "cutout.config.invalid_asset_slot_id", "asset_slot_id must be a stable lowercase slot ID"
        )
    if not SHA256.fullmatch(prompt_sha256):
        raise CutoutPreparationError(
            "cutout.config.invalid_prompt_sha256", "prompt_sha256 must be sha256:<64 lowercase hex>"
        )
    if not ROUTE.fullmatch(generation_route):
        raise CutoutPreparationError(
            "cutout.config.invalid_generation_route", "generation_route must be a stable lowercase route ID"
        )
    colors = list(dict.fromkeys(probe_colors or DEFAULT_PROBE_COLORS))
    for color in colors:
        _parse_color(color)
    if key_color is not None:
        _parse_color(key_color)
    if require_native_alpha and key_color is not None:
        raise CutoutPreparationError(
            "cutout.config.conflicting_alpha_route",
            "require_native_alpha and key_color are mutually exclusive acquisition routes",
        )
    if not require_native_alpha and key_color is None:
        raise CutoutPreparationError(
            "cutout.config.explicit_alpha_route_required",
            "select exactly one explicit acquisition route: require_native_alpha or controlled key_color",
        )
    source = _safe_source(source_path)
    if migration_probe_authority is None:
        if acquisition_report_path is None:
            raise CutoutPreparationError(
                "cutout.acquisition.report_required",
                "formal micro assets require a provider acquisition report and ordered attempt ledger",
            )
        if _has_symlink_component(acquisition_report_path.expanduser().absolute()):
            raise CutoutPreparationError(
                "cutout.path.symlink_forbidden",
                "acquisition report path cannot contain symbolic links",
            )
        expected_acquisition_mode = "native-alpha" if require_native_alpha else "controlled-key"
        acquisition = validate_acquisition_report(
            acquisition_report_path,
            source,
            article_id=article_id,
            asset_slot_id=asset_slot_id,
            prompt_sha256=prompt_sha256,
            generation_route=generation_route,
            expected_mode=expected_acquisition_mode,
            key_color=key_color,
            enforce_current_freshness=True,
            live_authority=live_authority,
            portable_trust_store=portable_trust_store,
            require_authority=True,
        )
        if not acquisition["ok"]:
            raise CutoutPreparationError(
                "cutout.acquisition.invalid",
                "; ".join(acquisition["errors"]),
            )
    else:
        acquisition = None
        required_probe_authority = {
            "kind": "org-wechat-migration-probe-processor-authority-v1",
            "validated": True,
            "migration_only": True,
            "article_asset_authority": False,
            "registerable": False,
            "portable": False,
            "carry_forward": False,
        }
        if any(
            migration_probe_authority.get(key) != value
            for key, value in required_probe_authority.items()
        ):
            raise CutoutPreparationError(
                "cutout.migration.authority_invalid",
                "migration probe processor authority is invalid or article-capable",
            )
        if (
            role != "floating-spot"
            or article_id != "migration-route-probe"
            or asset_slot_id != "migration.rgba-route-probe"
        ):
            raise CutoutPreparationError(
                "cutout.migration.scope_violation",
                "migration processor authority is limited to the neutral route probe",
            )
    output = _safe_new_path(output_path)
    report = _safe_new_path(report_path)
    if len({source, output, report}) != 3:
        raise CutoutPreparationError(
            "cutout.path.identity_conflict", "source, output, and report paths must be distinct"
        )
    try:
        with Image.open(source) as opened:
            opened.load()
            if opened.format != "PNG" or opened.mode not in {"RGB", "RGBA"}:
                raise CutoutPreparationError(
                    "cutout.source.unsupported_png",
                    "source must be an RGB or RGBA PNG; arbitrary formats are not normalized implicitly",
                )
            source_mode = opened.mode
            source_dimensions = opened.size
            source_image = opened.copy()
    except CutoutPreparationError:
        raise
    except (OSError, ValueError) as exc:
        raise CutoutPreparationError("cutout.source.unreadable", f"cannot decode source PNG: {exc}") from exc
    if min(source_dimensions) < 128 or max(source_dimensions) < 256:
        raise CutoutPreparationError(
            "cutout.source.minimum_dimensions", "source must be at least 256 px on one axis and 128 px on the other"
        )

    config = {
        "role": role,
        "key_color": key_color,
        "require_native_alpha": require_native_alpha,
        "border_ring_ratio": 0.04,
        "border_p95_limit_rgb": 32.0,
        "minimum_border_background_ratio": 0.985,
        "sure_distance_rgb": 18.0,
        "soft_distance_rgb": 120.0,
        "safety_margin_ratio": 0.03,
        "probe_colors": colors,
        "transparent_rgb_policy": "zero",
        "png_encoding": {"mode": "RGBA8", "interlace": False, "compress_level": 9},
    }
    background_assessment: dict[str, Any]
    mask_metrics: dict[str, Any] = {}
    edge_metrics: dict[str, Any] = {}
    has_native_alpha = (
        source_mode == "RGBA" and source_image.getchannel("A").getextrema()[0] < 255
    )
    if key_color is not None and has_native_alpha:
        raise CutoutPreparationError(
            "cutout.source.route_mismatch_native_rgba",
            "controlled-key attempt downloaded real native RGBA; rerun it as the explicit native-alpha route instead of mislabelling the processor path",
        )
    if require_native_alpha and not has_native_alpha:
        raise CutoutPreparationError(
            "cutout.source.native_alpha_required",
            "native-alpha attempt did not download a PNG with real transparent pixels; "
            "do not infer or remove a background in this attempt",
        )
    if has_native_alpha:
        native_safety = _validate_native_source_safety(source)
        if not native_safety["ok"]:
            raise CutoutPreparationError(
                "cutout.source.invalid_native_rgba",
                "native RGBA source failed pre-crop safety checks; regenerate rather than force-removing it: "
                + "; ".join(native_safety.get("errors", [])),
            )
        prepared = source_image.copy()
        background_assessment = {
            "source_background_removable": True,
            "native_alpha_accepted": True,
        }
        method = "native-rgba-normalize-v1"
    else:
        rgb = source_image.convert("RGB")
        observed_key, background_assessment = _background_assessment(
            rgb,
            requested_key=key_color,
            border_ring_ratio=config["border_ring_ratio"],
            border_p95_limit_rgb=config["border_p95_limit_rgb"],
            soft_distance_rgb=config["soft_distance_rgb"],
            minimum_border_background_ratio=config["minimum_border_background_ratio"],
        )
        prepared, mask_metrics, edge_metrics = _matte_key_background(
            rgb,
            observed_key,
            sure_distance_rgb=config["sure_distance_rgb"],
            soft_distance_rgb=config["soft_distance_rgb"],
        )
        method = "border-connected-chroma-matting-v1"
    prepared, crop_metrics = _clean_and_crop(prepared, role, config["safety_margin_ratio"])
    mask_metrics.update(crop_metrics)
    png = _png_bytes(prepared)
    validation = _validate_final_png(png, role, output.parent)
    output_sha256 = _sha256_bytes(png)
    inspection = validation["inspection"]
    script_sha256 = _sha256_file(Path(__file__).resolve())
    if migration_probe_authority is None:
        generation = {
            "route": generation_route,
            "prompt_sha256": prompt_sha256,
            "alpha_was_not_assumed": True,
            "acquisition_report_location": _relative_to_report(
                acquisition["report_path"], report  # type: ignore[index]
            ),
            "acquisition_report_sha256": acquisition["report_sha256"],  # type: ignore[index]
            "attempt_count": acquisition["attempt_count"],  # type: ignore[index]
            "accepted_attempt_index": acquisition["accepted_attempt_index"],  # type: ignore[index]
            "authority_binding_sha256": acquisition["authority"]["binding_sha256"],  # type: ignore[index]
            "authority_scope_at_creation": acquisition["authority"]["authority_mode"],  # type: ignore[index]
            "acquisition_assurance": acquisition["authority"]["assurance"],  # type: ignore[index]
            "operationally_accepted": acquisition["authority"][  # type: ignore[index]
                "operationally_accepted"
            ],
            "host_attested": acquisition["authority"]["host_attested"],  # type: ignore[index]
            "portable": acquisition["authority"]["portable"],  # type: ignore[index]
            "portable_host_receipt_verified": acquisition["authority"]["portable_verified"],  # type: ignore[index]
            "requires_live_authority_revalidation": acquisition["authority"][  # type: ignore[index]
                "requires_live_revalidation"
            ],
            "requires_current_session_chain_revalidation": acquisition["authority"][  # type: ignore[index]
                "requires_current_session_chain_revalidation"
            ],
            "policy_hook_evaluated": acquisition["authority"][  # type: ignore[index]
                "policy_hook_evaluated"
            ],
            "truth_boundary": (
                "Current-session acceptance is operator/harness-trusted, non-portable, and "
                "not host-attested. Registration and ready-for-layout revalidate the complete "
                "migration/request/create-once-ingestion/raw/RGBA chain. A Python policy hook "
                "may veto but cannot upgrade assurance. Portable assurance requires both "
                "verified Ed25519 receipts."
            ),
        }
        result_kind = "org-wechat-micro-cutout-derivation-v1"
        result_status = "approved"
    else:
        generation = {
            "route": generation_route,
            "prompt_sha256": prompt_sha256,
            "alpha_was_not_assumed": True,
            "authority_scope_at_creation": "migration-probe-only",
            "acquisition_assurance": "binding-and-create-once-ingestion-only",
            "operationally_accepted": False,
            "host_attested": False,
            "portable": False,
            "portable_host_receipt_verified": False,
            "requires_migration_finalization": True,
            "truth_boundary": (
                "This derivative proves only the local migration pixel chain. It has no "
                "article asset authority and cannot be registered, uploaded, copied, or "
                "carried into authoring. Current-session or portable migration finalization "
                "must independently validate the host trace."
            ),
        }
        result_kind = "org-wechat-migration-probe-cutout-derivation-v1"
        result_status = "migration-probe-only"

    result = {
        "schema_version": 1,
        "kind": result_kind,
        "status": result_status,
        "article_id": article_id,
        "asset_slot_id": asset_slot_id,
        "role": role,
        "location_base": "report-parent",
        "source": {
            "location": _relative_to_report(source, report),
            "file_sha256": _sha256_file(source),
            "pixel_sha256": _pixel_sha256(source_image),
            "format": "PNG",
            "mode": source_mode,
            "width_px": source_dimensions[0],
            "height_px": source_dimensions[1],
        },
        "generation": generation,
        "processor": {
            "method": method,
            "script": "scripts/prepare_micro_cutout.py",
            "script_sha256": script_sha256,
            "pillow_version": pillow_version,
            "config": config,
            "config_sha256": _canonical_sha256(config),
        },
        "background_assessment": background_assessment,
        "mask_metrics": mask_metrics,
        "edge_metrics": edge_metrics,
        "composite_probes": _composite_probes(prepared, colors),
        "output": {
            "location": _relative_to_report(output, report),
            "file_sha256": output_sha256,
            "pixel_sha256": _pixel_sha256(prepared),
            "mode": "RGBA8",
            "width_px": prepared.width,
            "height_px": prepared.height,
            "transparent_rgb_zeroed": True,
            "metadata_free": True,
        },
        "final_validation": {
            "ok": True,
            "error_codes": [],
            "inspection": inspection,
            "inspection_sha256": _canonical_sha256(inspection),
        },
    }
    if migration_probe_authority is not None:
        result["migration_probe"] = migration_probe_authority
    report_bytes = (
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    wrote_output = False
    try:
        with output.open("xb") as destination:
            destination.write(png)
        wrote_output = True
        with report.open("xb") as destination:
            destination.write(report_bytes)
    except OSError as exc:
        if wrote_output and output.is_file() and not output.is_symlink():
            try:
                if _sha256_file(output) == output_sha256:
                    output.unlink()
            except OSError:
                pass
        raise CutoutPreparationError("cutout.output.create_once", f"cannot create output bundle: {exc}") from exc
    return result


def prepare_micro_cutout(
    source_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    role: str,
    article_id: str,
    asset_slot_id: str,
    prompt_sha256: str,
    generation_route: str,
    acquisition_report_path: Path | None = None,
    key_color: str | None = None,
    require_native_alpha: bool = False,
    probe_colors: list[str] | None = None,
    live_authority: LiveAuthorityCallback | None = None,
    portable_trust_store: Path | None = None,
) -> dict[str, Any]:
    """Prepare one formal article cutout with full acquisition authority."""

    return _prepare_micro_cutout(
        source_path,
        output_path,
        report_path,
        role=role,
        article_id=article_id,
        asset_slot_id=asset_slot_id,
        prompt_sha256=prompt_sha256,
        generation_route=generation_route,
        acquisition_report_path=acquisition_report_path,
        key_color=key_color,
        require_native_alpha=require_native_alpha,
        probe_colors=probe_colors,
        live_authority=live_authority,
        portable_trust_store=portable_trust_store,
    )


def main() -> None:
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/prepare_micro_cutout.py")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--role", choices=sorted(ROLE_TARGET_RATIOS), required=True)
    parser.add_argument("--article-id", required=True)
    parser.add_argument("--asset-slot-id", required=True)
    parser.add_argument("--prompt-sha256", required=True)
    parser.add_argument("--generation-route", required=True)
    parser.add_argument("--acquisition-report", type=Path, required=True)
    parser.add_argument("--portable-trust-store", type=Path)
    parser.add_argument("--key-color")
    parser.add_argument("--require-native-alpha", action="store_true")
    parser.add_argument("--probe-color", action="append", dest="probe_colors")
    args = parser.parse_args()
    try:
        result = prepare_micro_cutout(
            args.source,
            args.output,
            args.report,
            role=args.role,
            article_id=args.article_id,
            asset_slot_id=args.asset_slot_id,
            prompt_sha256=args.prompt_sha256,
            generation_route=args.generation_route,
            acquisition_report_path=args.acquisition_report,
            portable_trust_store=args.portable_trust_store,
            key_color=args.key_color,
            require_native_alpha=args.require_native_alpha,
            probe_colors=args.probe_colors,
        )
    except CutoutPreparationError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1) from exc
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.absolute()),
                "report": str(args.report.absolute()),
                "sha256": result["output"]["file_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
