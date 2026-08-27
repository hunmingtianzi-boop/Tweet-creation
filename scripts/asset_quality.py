#!/usr/bin/env python3
"""Deterministic bitmap checks used by the WeChat visual workflow."""

from __future__ import annotations

import hashlib
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
    }
    if not has_alpha_channel:
        return result
    if bit_depth != 8 or color_type not in {4, 6} or compression != 0 or filtering != 0 or interlace != 0:
        result["alpha_analysis"] = "channel-present-but-pixels-not-decoded"
        return result
    channels = 2 if color_type == 4 else 4
    stride = width * channels
    compressed = b"".join(value for kind, value in chunks if kind == b"IDAT")
    try:
        raw = zlib.decompress(compressed)
    except zlib.error as exc:
        raise ValueError(f"PNG IDAT data cannot be decompressed: {exc}") from exc
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ValueError("PNG scanline data has an unexpected length")
    prior = bytearray(stride)
    transparent = 0
    visible = 0
    cursor = 0
    alpha_offset = channels - 1
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
        for index in range(alpha_offset, stride, channels):
            alpha = decoded[index]
            if alpha < 255:
                transparent += 1
            if alpha > 0:
                visible += 1
        prior = decoded
    pixels = width * height
    result.update(
        {
            "alpha_analysis": "decoded",
            "transparent_pixel_ratio": round(transparent / pixels, 6),
            "opaque_pixel_ratio": round((pixels - transparent) / pixels, 6),
            "has_transparent_pixels": transparent > 0,
            "has_visible_pixels": visible > 0,
        }
    )
    return result


def validate_micro_asset(path: Path, role: str) -> dict[str, Any]:
    errors: list[str] = []
    try:
        inspection = inspect_png(path)
    except (OSError, ValueError) as exc:
        return {"ok": False, "path": str(path), "role": role, "errors": [str(exc)]}
    if role not in ROLE_ASPECT_RATIOS:
        errors.append(f"unknown micro-visual role: {role}")
    else:
        minimum, maximum = ROLE_ASPECT_RATIOS[role]
        ratio = inspection["aspect_ratio"]
        if not minimum <= ratio <= maximum:
            errors.append(
                f"{role} aspect ratio must be between {minimum} and {maximum}; found {ratio}"
            )
    if inspection["width_px"] < 256 or inspection["height_px"] < 128:
        errors.append("micro asset must be at least 256 px wide and 128 px high")
    if not inspection["has_alpha_channel"]:
        errors.append("micro asset requires a real PNG alpha channel")
    if inspection.get("alpha_analysis") != "decoded":
        errors.append("micro asset alpha pixels must be deterministically decodable")
    elif not inspection["has_transparent_pixels"]:
        errors.append("micro asset alpha channel contains no transparent pixels")
    elif not inspection["has_visible_pixels"]:
        errors.append("micro asset is fully transparent")
    transparent_ratio = inspection.get("transparent_pixel_ratio")
    if isinstance(transparent_ratio, float) and transparent_ratio < 0.01:
        errors.append("micro asset has less than 1% transparent pixels; open edges are not credible")
    return {
        "ok": not errors,
        "path": str(path),
        "role": role,
        "inspection": inspection,
        "errors": errors,
    }
