#!/usr/bin/env python3
"""Robust, privacy-preserving authenticated payloads for opaque PNG artwork.

The watermark is carried by repeated comparisons of two mid-frequency DCT
coefficients on a normalized luminance canvas.  It is deliberately independent
of PNG chunks, EXIF data, and pixel least-significant bits, so ordinary metadata
stripping does not remove it.  The normalized canvas tolerates the tested
whole-frame resize; V1 makes no robustness claim for crop, added borders, or
rotation.

Only a random 64-bit opaque identifier, a format version/purpose nibble, an
8-bit key epoch, and a truncated
HMAC are embedded.  Public reports expose a one-way payload fingerprint rather
than the identifier.  CLI keys are read from an environment variable and are
never included in reports or error messages.  A successful result authenticates
the embedded payload under the supplied key; by itself it does not prove legal
authorship, publication, or survival through the real WeChat transport.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import io
import json
import math
import os
import secrets
import stat
import struct
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/provenance_watermark.py")

try:
    from PIL import Image, ImageFilter, ImageStat
except ImportError as exc:  # pragma: no cover - exercised only on misconfigured hosts
    raise RuntimeError("provenance_watermark requires Pillow") from exc


ALGORITHM = "org-wechat-dct-v1"
SCHEMA_VERSION = 1
PAYLOAD_VERSION = 1
PAYLOAD_PURPOSE = 1
DEFAULT_KEY_ENV = "PROVENANCE_WATERMARK_KEY"
PRIVATE_ROOT_ENV = "PROVENANCE_WATERMARK_PRIVATE_ROOT"

# A 48 x 64 grid provides 3,072 distinct 8 x 8 blocks.  The compact 128-bit
# payload consumes 1,920 of them at fifteen independent repetitions per bit.
CANONICAL_SIZE = (384, 512)
BLOCK_SIZE = 8
REPETITIONS = 15
HMAC_TAG_BYTES = 6
WM_ID_BYTES = 8
PAYLOAD_HEADER_BYTES = 10
PAYLOAD_BYTES = PAYLOAD_HEADER_BYTES + HMAC_TAG_BYTES
PAYLOAD_BITS = PAYLOAD_BYTES * 8
REQUIRED_BLOCKS = PAYLOAD_BITS * REPETITIONS

MIN_WIDTH = 320
MIN_HEIGHT = 320
MIN_PIXELS = 160_000
MIN_TEXTURE_STDDEV = 8.0
MIN_DETAIL_RMS = 1.35
QUANTIZATION_STEP = 32.0
EMBED_ITERATIONS = 3
RESIDUAL_GAIN = 1.12
MIN_PSNR_DB = 42.0

# Resource limits apply before Pillow decodes pixel buffers.  V1 artwork is far
# below these ceilings, while hostile containers and accidental giant exports
# fail without consuming unbounded memory.
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_EMBED_PIXELS = 1_500_000
MAX_IMAGE_EDGE = 12_000
MAX_ASPECT_RATIO = 12.0
MIN_DETECTION_EDGE = 96

_RESAMPLING = getattr(Image, "Resampling", Image)


class WatermarkError(ValueError):
    """Base class for safe, user-actionable watermark failures."""


class CarrierRejectedError(WatermarkError):
    """Raised when a V1 carrier does not meet the opaque PNG policy."""

    def __init__(self, assessment: dict[str, Any]):
        self.assessment = assessment
        reason = assessment.get("reason") or "carrier is not eligible"
        super().__init__(reason)


class VerificationError(WatermarkError):
    """Raised when a newly embedded derivative cannot verify locally."""


@dataclass(frozen=True)
class _LoadedImage:
    image: Image.Image
    image_format: str | None
    input_bytes: int
    input_sha256: str


def _decode_image_bytes(encoded_image: bytes, *, label: str) -> _LoadedImage:
    if not encoded_image:
        raise WatermarkError(f"{label} must not be empty")
    if len(encoded_image) > MAX_INPUT_BYTES:
        raise WatermarkError(f"{label} exceeds the {MAX_INPUT_BYTES}-byte input limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(encoded_image)) as opened:
                width, height = opened.size
                if width <= 0 or height <= 0:
                    raise WatermarkError(f"{label} has invalid dimensions")
                if width > MAX_IMAGE_EDGE or height > MAX_IMAGE_EDGE:
                    raise WatermarkError(f"{label} exceeds the {MAX_IMAGE_EDGE}-pixel edge limit")
                if width * height > MAX_IMAGE_PIXELS:
                    raise WatermarkError(f"{label} exceeds the {MAX_IMAGE_PIXELS}-pixel image limit")
                if max(width, height) / min(width, height) > MAX_ASPECT_RATIO:
                    raise WatermarkError(
                        f"{label} exceeds the {MAX_ASPECT_RATIO:g}:1 aspect-ratio limit"
                    )
                if getattr(opened, "n_frames", 1) != 1 or getattr(opened, "is_animated", False):
                    raise WatermarkError(f"{label} must contain exactly one non-animated frame")
                image_format = opened.format
                opened.load()
                detached = opened.copy()
                detached.info = dict(opened.info)
    except WatermarkError:
        raise
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise WatermarkError(f"{label} cannot be safely decoded") from exc
    return _LoadedImage(
        image=detached,
        image_format=image_format,
        input_bytes=len(encoded_image),
        input_sha256=hashlib.sha256(encoded_image).hexdigest(),
    )


def _safe_load_image(path: str | Path, *, label: str) -> _LoadedImage:
    """Load one bounded, regular, non-symlink image into detached memory."""
    source_path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source_path, flags)
    except OSError as exc:
        raise WatermarkError(f"{label} must be an accessible regular file") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise WatermarkError(f"{label} must be a regular file")
        if metadata.st_size <= 0:
            raise WatermarkError(f"{label} must not be empty")
        if metadata.st_size > MAX_INPUT_BYTES:
            raise WatermarkError(f"{label} exceeds the {MAX_INPUT_BYTES}-byte input limit")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            total_bytes = 0
            encoded_chunks: list[bytes] = []
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                total_bytes += len(chunk)
                if total_bytes > MAX_INPUT_BYTES:
                    raise WatermarkError(f"{label} exceeds the {MAX_INPUT_BYTES}-byte input limit")
                encoded_chunks.append(chunk)
            final_metadata = os.fstat(stream.fileno())
            if (
                total_bytes != metadata.st_size
                or final_metadata.st_size != metadata.st_size
                or final_metadata.st_mtime_ns != metadata.st_mtime_ns
            ):
                raise WatermarkError(f"{label} changed while it was being read")
        return _decode_image_bytes(b"".join(encoded_chunks), label=label)
    except WatermarkError:
        raise
    except (OSError, ValueError) as exc:
        raise WatermarkError(f"{label} cannot be safely read") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 of a file without loading it all into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_key_text(value: str) -> bytes:
    if value.startswith("hex:"):
        try:
            return bytes.fromhex(value[4:])
        except ValueError as exc:
            raise WatermarkError("watermark key has invalid hex encoding") from exc
    if value.startswith("base64:"):
        try:
            return base64.b64decode(value[7:], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise WatermarkError("watermark key has invalid base64 encoding") from exc
    raise WatermarkError("text watermark keys must use hex: or base64: encoding")


def _resolve_key(key: bytes | str | None, *, key_env: str = DEFAULT_KEY_ENV) -> bytes:
    if key is None:
        value = os.environ.get(key_env)
        if value is None:
            raise WatermarkError(f"watermark key is required in environment variable {key_env}")
        material = _decode_key_text(value)
    elif isinstance(key, bytes):
        material = key
    elif isinstance(key, str):
        material = _decode_key_text(key)
    else:
        raise TypeError("key must be bytes, str, or None")
    if len(material) < 32:
        raise WatermarkError("watermark key must contain at least 32 bytes")
    return material


def _derive_key(key: bytes, label: bytes) -> bytes:
    return hmac.new(key, b"org-wechat-watermark\x00" + label, hashlib.sha256).digest()


def _keystream(key: bytes, label: bytes, length: int) -> bytes:
    derived = _derive_key(key, label)
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hmac.new(derived, struct.pack(">I", counter), hashlib.sha256).digest())
        counter += 1
    return bytes(output[:length])


def _parse_wm_id(value: bytes | str | None) -> bytes:
    if value is None:
        return secrets.token_bytes(WM_ID_BYTES)
    if isinstance(value, str):
        try:
            decoded = bytes.fromhex(value)
        except ValueError as exc:
            raise WatermarkError("explicit wm_id must be 16 hexadecimal characters") from exc
    elif isinstance(value, bytes):
        decoded = value
    else:
        raise TypeError("wm_id must be bytes, hexadecimal str, or None")
    if len(decoded) != WM_ID_BYTES:
        raise WatermarkError("explicit wm_id must contain exactly 8 bytes")
    return decoded


def _payload_fingerprint(header: bytes, key: bytes) -> str:
    fingerprint_key = _derive_key(key, b"public-payload-fingerprint-v1")
    return hmac.new(fingerprint_key, header, hashlib.sha256).hexdigest()


def _pack_payload(key: bytes, key_epoch: int, wm_id: bytes) -> tuple[bytes, str]:
    if isinstance(key_epoch, bool) or not isinstance(key_epoch, int) or not 0 <= key_epoch <= 0xFF:
        raise WatermarkError("key_epoch must be an integer from 0 through 255")
    type_byte = (PAYLOAD_VERSION << 4) | PAYLOAD_PURPOSE
    header = bytes((type_byte, key_epoch)) + wm_id
    auth_key = _derive_key(key, b"payload-auth-v1")
    tag = hmac.new(auth_key, header, hashlib.sha256).digest()[:HMAC_TAG_BYTES]
    raw = header + tag
    mask = _keystream(key, b"payload-mask-v1", len(raw))
    encoded = bytes(left ^ right for left, right in zip(raw, mask))
    return encoded, _payload_fingerprint(header, key)


def _unpack_payload(encoded: bytes, key: bytes) -> dict[str, Any] | None:
    if len(encoded) != PAYLOAD_BYTES:
        return None
    mask = _keystream(key, b"payload-mask-v1", len(encoded))
    raw = bytes(left ^ right for left, right in zip(encoded, mask))
    header, supplied_tag = raw[:-HMAC_TAG_BYTES], raw[-HMAC_TAG_BYTES:]
    auth_key = _derive_key(key, b"payload-auth-v1")
    expected_tag = hmac.new(auth_key, header, hashlib.sha256).digest()[:HMAC_TAG_BYTES]
    if not hmac.compare_digest(supplied_tag, expected_tag):
        return None
    if len(header) != PAYLOAD_HEADER_BYTES:
        return None
    version = header[0] >> 4
    purpose = header[0] & 0x0F
    key_epoch = header[1]
    wm_id = header[2:]
    if version != PAYLOAD_VERSION or purpose != PAYLOAD_PURPOSE or len(wm_id) != WM_ID_BYTES:
        return None
    return {
        "version": version,
        "purpose": purpose,
        "key_epoch": key_epoch,
        "wm_id": wm_id,
        "payload_fingerprint": _payload_fingerprint(header, key),
    }


def _bytes_to_bits(value: bytes) -> list[int]:
    return [(byte >> shift) & 1 for byte in value for shift in range(7, -1, -1)]


def _bits_to_bytes(bits: Sequence[int]) -> bytes:
    if len(bits) % 8:
        raise ValueError("bit sequence length must be a multiple of eight")
    output = bytearray()
    for offset in range(0, len(bits), 8):
        byte = 0
        for bit in bits[offset : offset + 8]:
            byte = (byte << 1) | int(bool(bit))
        output.append(byte)
    return bytes(output)


def _block_order(key: bytes) -> list[int]:
    columns = CANONICAL_SIZE[0] // BLOCK_SIZE
    rows = CANONICAL_SIZE[1] // BLOCK_SIZE
    placement_key = _derive_key(key, b"block-placement-v1")
    ranked = []
    for index in range(columns * rows):
        rank = hmac.new(placement_key, struct.pack(">I", index), hashlib.sha256).digest()[:16]
        ranked.append((rank, index))
    ranked.sort()
    return [index for _, index in ranked[:REQUIRED_BLOCKS]]


def _basis_difference() -> tuple[float, ...]:
    # Both coefficients are in the JPEG mid-frequency region.  The orthonormal
    # basis difference has squared norm two, used by _embedding_residual.
    first = (2, 3)
    second = (3, 2)

    def basis(u: int, v: int, x: int, y: int) -> float:
        alpha_u = 1 / math.sqrt(8) if u == 0 else 0.5
        alpha_v = 1 / math.sqrt(8) if v == 0 else 0.5
        return (
            alpha_u
            * alpha_v
            * math.cos((2 * x + 1) * u * math.pi / 16)
            * math.cos((2 * y + 1) * v * math.pi / 16)
        )

    return tuple(
        basis(*first, x, y) - basis(*second, x, y)
        for y in range(BLOCK_SIZE)
        for x in range(BLOCK_SIZE)
    )


_BASIS_DIFFERENCE = _basis_difference()
_BASIS_NORM_SQUARED = sum(value * value for value in _BASIS_DIFFERENCE)


def _canonical_luma(image: Image.Image) -> list[float]:
    channel = image.convert("YCbCr").getchannel("Y")
    normalized = channel.resize(CANONICAL_SIZE, _RESAMPLING.LANCZOS)
    return [float(value) for value in normalized.getdata()]


def _coefficient_difference(pixels: Sequence[float], block_index: int) -> float:
    canvas_width = CANONICAL_SIZE[0]
    block_columns = canvas_width // BLOCK_SIZE
    origin_x = (block_index % block_columns) * BLOCK_SIZE
    origin_y = (block_index // block_columns) * BLOCK_SIZE
    coefficient = 0.0
    basis_offset = 0
    for local_y in range(BLOCK_SIZE):
        offset = (origin_y + local_y) * canvas_width + origin_x
        for local_x in range(BLOCK_SIZE):
            coefficient += pixels[offset + local_x] * _BASIS_DIFFERENCE[basis_offset]
            basis_offset += 1
    return coefficient


def _embedding_residual(
    pixels: Sequence[float], bits: Sequence[int], order: Sequence[int]
) -> list[float]:
    residual = [0.0] * (CANONICAL_SIZE[0] * CANONICAL_SIZE[1])
    canvas_width = CANONICAL_SIZE[0]
    block_columns = canvas_width // BLOCK_SIZE
    for bit_index, bit in enumerate(bits):
        for repeat in range(REPETITIONS):
            block_index = order[bit_index * REPETITIONS + repeat]
            current = _coefficient_difference(pixels, block_index)
            nearest = math.floor(current / QUANTIZATION_STEP + 0.5)
            if nearest % 2 != bit:
                lower = nearest - 1
                upper = nearest + 1
                nearest = min(
                    (lower, upper),
                    key=lambda candidate: abs(candidate * QUANTIZATION_STEP - current),
                )
            # Centering every carrier coefficient in its parity bin creates a
            # half-step guard band while bounding host distortion.
            adjustment = nearest * QUANTIZATION_STEP - current
            origin_x = (block_index % block_columns) * BLOCK_SIZE
            origin_y = (block_index // block_columns) * BLOCK_SIZE
            basis_offset = 0
            for local_y in range(BLOCK_SIZE):
                offset = (origin_y + local_y) * canvas_width + origin_x
                for local_x in range(BLOCK_SIZE):
                    residual[offset + local_x] += (
                        adjustment
                        * _BASIS_DIFFERENCE[basis_offset]
                        / _BASIS_NORM_SQUARED
                    )
                    basis_offset += 1
    return residual


def _apply_residual(image: Image.Image, residual: Sequence[float]) -> Image.Image:
    residual_image = Image.new("F", CANONICAL_SIZE)
    residual_image.putdata(residual)
    projected = residual_image.resize(image.size, _RESAMPLING.BICUBIC)
    deltas = projected.getdata()
    rgb = image.convert("RGB")
    adjusted: list[tuple[int, int, int]] = []
    for (red, green, blue), delta in zip(rgb.getdata(), deltas):
        shift = float(delta) * RESIDUAL_GAIN
        adjusted.append(
            (
                max(0, min(255, int(round(red + shift)))),
                max(0, min(255, int(round(green + shift)))),
                max(0, min(255, int(round(blue + shift)))),
            )
        )
    result = Image.new("RGB", image.size)
    result.putdata(adjusted)
    return result


def _decode_bits(image: Image.Image, key: bytes) -> tuple[bytes, float, float]:
    pixels = _canonical_luma(image)
    order = _block_order(key)
    bits: list[int] = []
    agreements: list[float] = []
    margins: list[float] = []
    for bit_index in range(PAYLOAD_BITS):
        values = [
            _coefficient_difference(pixels, order[bit_index * REPETITIONS + repeat])
            for repeat in range(REPETITIONS)
        ]
        decoded_values = [math.floor(value / QUANTIZATION_STEP + 0.5) % 2 for value in values]
        ones = sum(decoded_values)
        bits.append(1 if ones > REPETITIONS // 2 else 0)
        agreements.append(max(ones, REPETITIONS - ones) / REPETITIONS)
        for value in values:
            nearest = math.floor(value / QUANTIZATION_STEP + 0.5)
            distance_from_center = abs(value - nearest * QUANTIZATION_STEP)
            margins.append(max(0.0, QUANTIZATION_STEP / 2 - distance_from_center))
    repeat_vote_agreement = sum(agreements) / len(agreements)
    mean_margin = sum(margins) / len(margins)
    return _bits_to_bytes(bits), repeat_vote_agreement, mean_margin


def _texture_metrics(image: Image.Image) -> tuple[float, float]:
    sample = image.convert("L")
    sample.thumbnail((256, 256), _RESAMPLING.LANCZOS)
    texture_stddev = float(ImageStat.Stat(sample).stddev[0])
    low_pass = sample.filter(ImageFilter.GaussianBlur(radius=1.5))
    source_values = sample.getdata()
    low_values = low_pass.getdata()
    count = sample.width * sample.height or 1
    detail_rms = math.sqrt(
        sum((int(source) - int(smooth)) ** 2 for source, smooth in zip(source_values, low_values))
        / count
    )
    return texture_stddev, detail_rms


def assess_carrier(path: str | Path) -> dict[str, Any]:
    """Assess whether *path* is an eligible V1 embedding carrier.

    V1 intentionally rejects transparency, non-PNG formats, indexed/grayscale
    inputs, small canvases, and extremely smooth images.  Detection is more
    permissive because a WeChat transport derivative may be JPEG or resized.
    """
    source_path = Path(path)
    reason_codes: list[str] = []
    messages: list[str] = []
    report: dict[str, Any] = {
        "eligible": False,
        "reason_codes": reason_codes,
        "width": None,
        "height": None,
        "mode": None,
        "format": None,
        "opaque": False,
        "texture_stddev": None,
        "detail_rms": None,
        "input_sha256": None,
        "input_bytes": None,
    }
    try:
        loaded = _safe_load_image(source_path, label="carrier image")
        opened = loaded.image
        report.update(
            {
                "width": opened.width,
                "height": opened.height,
                "mode": opened.mode,
                "format": loaded.image_format,
                "input_sha256": loaded.input_sha256,
                "input_bytes": loaded.input_bytes,
            }
        )
        if loaded.image_format != "PNG":
            reason_codes.append("format_not_png")
            messages.append("V1 embedding requires a PNG input")
        if opened.mode not in {"RGB", "RGBA"}:
            reason_codes.append("unsupported_color_mode")
            messages.append("V1 embedding requires RGB or RGBA pixels")
        opaque = opened.mode == "RGB" and "transparency" not in opened.info
        if opened.mode == "RGB" and "transparency" in opened.info:
            reason_codes.append("transparent_pixels")
            messages.append("V1 rejects carriers containing transparent pixels")
        if opened.mode == "RGBA":
            opaque = opened.getchannel("A").getextrema() == (255, 255)
            if not opaque:
                reason_codes.append("transparent_pixels")
                messages.append("V1 rejects carriers containing transparent pixels")
        report["opaque"] = opaque
        if opened.width < MIN_WIDTH or opened.height < MIN_HEIGHT or opened.width * opened.height < MIN_PIXELS:
            reason_codes.append("carrier_too_small")
            messages.append(
                f"V1 requires at least {MIN_WIDTH}x{MIN_HEIGHT} pixels and {MIN_PIXELS} total pixels"
            )
        if opened.width * opened.height > MAX_EMBED_PIXELS:
            reason_codes.append("carrier_too_large_for_embedding")
            messages.append(
                f"V1 embedding is limited to {MAX_EMBED_PIXELS} pixels for bounded memory use"
            )
        texture_stddev, detail_rms = _texture_metrics(opened)
        report["texture_stddev"] = round(texture_stddev, 4)
        report["detail_rms"] = round(detail_rms, 4)
        if texture_stddev < MIN_TEXTURE_STDDEV or detail_rms < MIN_DETAIL_RMS:
            reason_codes.append("insufficient_texture")
            messages.append("carrier texture is too weak for an imperceptible robust watermark")
    except WatermarkError as exc:
        reason_codes.append("unsafe_or_unreadable_image")
        messages.append(str(exc))
    report["eligible"] = not reason_codes
    report["reason"] = messages[0] if messages else None
    return report


def _public_detection_report(
    image: Image.Image,
    image_format: str | None,
    decoded: dict[str, Any] | None,
    repeat_vote_agreement: float,
    mean_margin: float,
    input_sha256: str,
    input_bytes: int,
    *,
    include_private_record: bool,
) -> dict[str, Any]:
    payload_authenticated = decoded is not None
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "payload_authenticated" if payload_authenticated else "not_detected",
        "algorithm": ALGORITHM,
        "detected": payload_authenticated,
        "authenticated": payload_authenticated,
        "payload_fingerprint": decoded["payload_fingerprint"] if decoded else None,
        "version": decoded["version"] if decoded else None,
        "purpose": decoded["purpose"] if decoded else None,
        "key_epoch": decoded["key_epoch"] if decoded else None,
        "repeat_vote_agreement": round(repeat_vote_agreement, 6),
        "mean_abs_margin": round(mean_margin, 4),
        "input_sha256": input_sha256,
        "input_bytes": input_bytes,
        "image": {
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "format": image_format,
        },
    }
    if include_private_record and decoded:
        report["private_record"] = {
            "wm_id": decoded["wm_id"].hex(),
            "payload_fingerprint": decoded["payload_fingerprint"],
            "version": decoded["version"],
            "purpose": decoded["purpose"],
            "key_epoch": decoded["key_epoch"],
        }
    public_report = _strict_public_report(report)
    if include_private_record and decoded:
        public_report["private_record"] = _strict_private_record(report["private_record"])
    return public_report


def detect_watermark(
    path: str | Path,
    *,
    key: bytes | str | None = None,
    key_env: str = DEFAULT_KEY_ENV,
    include_private_record: bool = False,
) -> dict[str, Any]:
    """Detect and authenticate a payload in one bounded PNG/JPEG image.

    ``authenticated=True`` means only that the recovered compact payload has a
    valid HMAC under ``key``.  It is not a publication or authorship verdict.
    """
    secret = _resolve_key(key, key_env=key_env)
    loaded = _safe_load_image(path, label="detection image")
    if loaded.image_format not in {"PNG", "JPEG"}:
        raise WatermarkError("detection image must be PNG or JPEG")
    if loaded.image.width < MIN_DETECTION_EDGE or loaded.image.height < MIN_DETECTION_EDGE:
        raise WatermarkError("detection image is too small")
    return _detect_image(
        loaded.image,
        image_format=loaded.image_format,
        input_sha256=loaded.input_sha256,
        input_bytes=loaded.input_bytes,
        key=secret,
        include_private_record=include_private_record,
    )


def _detect_image(
    image: Image.Image,
    *,
    image_format: str | None,
    input_sha256: str,
    input_bytes: int,
    key: bytes,
    include_private_record: bool = False,
) -> dict[str, Any]:
    encoded, repeat_vote_agreement, mean_margin = _decode_bits(image, key)
    decoded = _unpack_payload(encoded, key)
    return _public_detection_report(
        image,
        image_format,
        decoded,
        repeat_vote_agreement,
        mean_margin,
        input_sha256,
        input_bytes,
        include_private_record=include_private_record,
    )


def _psnr(before: Image.Image, after: Image.Image) -> float:
    left = before.convert("RGB")
    right = after.convert("RGB")
    if left.size != right.size:
        raise ValueError("PSNR images must have identical dimensions")
    squared_error = 0
    count = left.width * left.height * 3
    for original, watermarked in zip(left.getdata(), right.getdata()):
        squared_error += sum((a - b) ** 2 for a, b in zip(original, watermarked))
    if squared_error == 0:
        return math.inf
    mse = squared_error / count
    return 10 * math.log10((255 * 255) / mse)


def _require_opaque_png(loaded: _LoadedImage, *, label: str) -> None:
    image = loaded.image
    if loaded.image_format != "PNG" or image.mode not in {"RGB", "RGBA"}:
        raise WatermarkError(f"{label} must be an RGB or RGBA PNG")
    if "transparency" in image.info:
        raise WatermarkError(f"{label} must be fully opaque")
    if image.mode == "RGBA" and image.getchannel("A").getextrema() != (255, 255):
        raise WatermarkError(f"{label} must be fully opaque")


def measure_psnr(source_path: str | Path, marked_path: str | Path) -> float:
    """Independently measure RGB PSNR for two same-sized opaque PNGs.

    Registry validation uses this public helper instead of trusting a number
    stored in an embed report.  Inputs receive the same resource-limit checks as
    embed/detect, and neither image is resized implicitly.
    """
    source = _safe_load_image(source_path, label="PSNR source image")
    marked = _safe_load_image(marked_path, label="PSNR marked image")
    _require_opaque_png(source, label="PSNR source image")
    _require_opaque_png(marked, label="PSNR marked image")
    if source.image.size != marked.image.size:
        raise WatermarkError("PSNR images must have identical dimensions")
    return _psnr(source.image, marked.image)


def _simulate_transport(
    derivative: Image.Image,
    *,
    key: bytes,
    expected_fingerprint: str,
) -> dict[str, Any]:
    """Run the mandatory local width-390/JPEG-Q75 authentication gate."""
    frame = derivative.convert("RGB")
    if frame.width > 390:
        target_height = max(1, round(frame.height * 390 / frame.width))
        frame = frame.resize((390, target_height), _RESAMPLING.LANCZOS)
    if frame.width < MIN_DETECTION_EDGE or frame.height < MIN_DETECTION_EDGE:
        raise VerificationError("transport simulation frame is too small for authentication")
    buffer = io.BytesIO()
    frame.save(buffer, format="JPEG", quality=75, subsampling=2)
    encoded_jpeg = buffer.getvalue()
    simulated_sha256 = hashlib.sha256(encoded_jpeg).hexdigest()
    try:
        with Image.open(io.BytesIO(encoded_jpeg)) as opened:
            opened.load()
            decoded_frame = opened.convert("RGB")
    except (OSError, ValueError) as exc:  # generated bytes, but still fail closed
        raise VerificationError("transport simulation JPEG could not be decoded") from exc
    detection = _detect_image(
        decoded_frame,
        image_format="JPEG",
        input_sha256=simulated_sha256,
        input_bytes=len(encoded_jpeg),
        key=key,
    )
    payload_authenticated = bool(
        detection["authenticated"]
        and detection["payload_fingerprint"] == expected_fingerprint
    )
    report = {
        "profile": "final-frame-width-390-if-larger-jpeg-q75",
        "status": "payload_authenticated" if payload_authenticated else "not_detected",
        "payload_authenticated": payload_authenticated,
        "payload_fingerprint": detection["payload_fingerprint"] if payload_authenticated else None,
        "width": decoded_frame.width,
        "height": decoded_frame.height,
        "jpeg_quality": 75,
        "simulated_sha256": simulated_sha256,
        "simulated_bytes": len(encoded_jpeg),
        "repeat_vote_agreement": detection["repeat_vote_agreement"],
    }
    if not payload_authenticated:
        raise VerificationError(
            "watermark payload failed width-390/JPEG-Q75 transport simulation authentication"
        )
    return _copy_allowlisted(report, _TRANSPORT_SIMULATION_PUBLIC_SCHEMA)


def verify_transport_simulation(
    marked_path: str | Path,
    *,
    key: bytes | str | None = None,
    key_env: str = DEFAULT_KEY_ENV,
) -> dict[str, Any]:
    """Independently rerun the mandatory 390-if-larger/JPEG-Q75 gate."""
    secret = _resolve_key(key, key_env=key_env)
    loaded = _safe_load_image(marked_path, label="marked image")
    _require_opaque_png(loaded, label="marked image")
    if loaded.image.width < MIN_DETECTION_EDGE or loaded.image.height < MIN_DETECTION_EDGE:
        raise WatermarkError("marked image is too small for payload authentication")
    direct_detection = _detect_image(
        loaded.image,
        image_format=loaded.image_format,
        input_sha256=loaded.input_sha256,
        input_bytes=loaded.input_bytes,
        key=secret,
    )
    if not direct_detection["authenticated"]:
        raise VerificationError("marked image payload is not authenticated before simulation")
    return _simulate_transport(
        loaded.image,
        key=secret,
        expected_fingerprint=direct_detection["payload_fingerprint"],
    )


def _require_new_path(path: Path, *, label: str) -> None:
    if os.path.lexists(path):
        raise WatermarkError(f"{label} already exists; replacement is forbidden")


def _publish_bytes_exclusive(
    destination_path: Path,
    data: bytes,
    *,
    label: str,
    mode: int = 0o600,
) -> None:
    """Publish complete bytes with an exclusive link from a private dirfd."""
    _require_new_path(destination_path, label=label)
    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = destination_path.parent.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WatermarkError(f"{label} directory cannot be prepared") from exc
    actual_destination = resolved_parent / destination_path.name
    _require_new_path(actual_destination, label=label)
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor = -1
    staging_descriptor = -1
    payload_descriptor = -1
    staging_name: str | None = None
    try:
        parent_descriptor = os.open(resolved_parent, directory_flags)
        for _ in range(128):
            candidate = f".provenance-stage-{secrets.token_hex(12)}"
            try:
                os.mkdir(candidate, 0o700, dir_fd=parent_descriptor)
                staging_name = candidate
                break
            except FileExistsError:
                continue
        if staging_name is None:
            raise WatermarkError(f"{label} staging directory could not be allocated")
        staging_descriptor = os.open(
            staging_name,
            directory_flags,
            dir_fd=parent_descriptor,
        )
        payload_descriptor = os.open(
            "payload",
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=staging_descriptor,
        )
        remaining = memoryview(data)
        while remaining:
            written = os.write(payload_descriptor, remaining)
            if written <= 0:
                raise WatermarkError(f"{label} staging write did not make progress")
            remaining = remaining[written:]
        os.fsync(payload_descriptor)
        source_metadata = os.fstat(payload_descriptor)
        os.link(
            "payload",
            actual_destination.name,
            src_dir_fd=staging_descriptor,
            dst_dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        destination_metadata = os.stat(
            actual_destination.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            source_metadata.st_dev != destination_metadata.st_dev
            or source_metadata.st_ino != destination_metadata.st_ino
        ):
            raise WatermarkError(f"{label} atomic commit inode verification failed")
    except FileExistsError as exc:
        raise WatermarkError(f"{label} already exists; replacement is forbidden") from exc
    except WatermarkError:
        raise
    except OSError as exc:
        raise WatermarkError(f"{label} could not be committed atomically") from exc
    finally:
        if payload_descriptor >= 0:
            os.close(payload_descriptor)
        if staging_descriptor >= 0:
            try:
                os.unlink("payload", dir_fd=staging_descriptor)
            except FileNotFoundError:
                pass
            finally:
                os.close(staging_descriptor)
        if parent_descriptor >= 0:
            if staging_name is not None:
                try:
                    os.rmdir(staging_name, dir_fd=parent_descriptor)
                except OSError:
                    pass
            os.close(parent_descriptor)


def embed_watermark(
    input_path: str | Path,
    output_path: str | Path,
    *,
    key: bytes | str | None = None,
    key_env: str = DEFAULT_KEY_ENV,
    key_epoch: int = 1,
    wm_id: bytes | str | None = None,
    include_private_record: bool = False,
) -> dict[str, Any]:
    """Create a new watermarked PNG derivative and verify it locally.

    The source path and output path must differ.  ``wm_id`` exists for
    deterministic tests and controlled migrations; production callers should
    omit it so a cryptographically random identifier is generated.
    """
    source_path = Path(input_path)
    destination_path = Path(output_path)
    _require_new_path(destination_path, label="watermarked image output")
    if source_path.resolve() == destination_path.resolve():
        raise WatermarkError("output must be a new derivative path; source overwrite is forbidden")
    if destination_path.suffix.lower() != ".png":
        raise WatermarkError("watermarked derivative must use a .png output path")
    assessment = assess_carrier(source_path)
    if not assessment["eligible"]:
        raise CarrierRejectedError(assessment)

    loaded_source = _safe_load_image(source_path, label="carrier image")
    if loaded_source.input_sha256 != assessment["input_sha256"]:
        raise WatermarkError("carrier image changed during eligibility assessment")
    _require_opaque_png(loaded_source, label="carrier image")

    secret = _resolve_key(key, key_env=key_env)
    identifier = _parse_wm_id(wm_id)
    encoded_payload, expected_fingerprint = _pack_payload(secret, key_epoch, identifier)
    bits = _bytes_to_bits(encoded_payload)
    order = _block_order(secret)

    source_image = loaded_source.image
    source_mode = source_image.mode
    source_alpha = source_image.getchannel("A").copy() if source_mode == "RGBA" else None
    original_rgb = source_image.convert("RGB")

    watermarked = original_rgb.copy()
    for _ in range(EMBED_ITERATIONS):
        canonical = _canonical_luma(watermarked)
        residual = _embedding_residual(canonical, bits, order)
        if not any(residual):
            break
        watermarked = _apply_residual(watermarked, residual)

    if source_alpha is not None:
        rgba = watermarked.convert("RGBA")
        rgba.putalpha(source_alpha)
        derivative: Image.Image = rgba
    else:
        derivative = watermarked

    psnr_db = _psnr(original_rgb, derivative)
    if not math.isfinite(psnr_db):
        raise VerificationError("watermark embedding did not create a measurable pixel derivative")
    if psnr_db < MIN_PSNR_DB:
        raise VerificationError(
            f"new watermark derivative PSNR {psnr_db:.4f} dB is below the {MIN_PSNR_DB:.1f} dB threshold"
        )

    transport_simulation = _simulate_transport(
        derivative,
        key=secret,
        expected_fingerprint=expected_fingerprint,
    )

    try:
        encoded_output = io.BytesIO()
        derivative.save(encoded_output, format="PNG", optimize=True)
        output_bytes = encoded_output.getvalue()
    except (OSError, ValueError) as exc:
        raise WatermarkError("watermarked image could not be encoded") from exc
    loaded_derivative = _decode_image_bytes(output_bytes, label="watermarked image")
    _require_opaque_png(loaded_derivative, label="watermarked image")
    detection = _detect_image(
        loaded_derivative.image,
        image_format=loaded_derivative.image_format,
        input_sha256=loaded_derivative.input_sha256,
        input_bytes=loaded_derivative.input_bytes,
        key=secret,
    )
    if not detection["authenticated"] or detection["payload_fingerprint"] != expected_fingerprint:
        raise VerificationError("new watermark derivative failed local authentication")
    post_sha256 = detection["input_sha256"]
    current_source = _safe_load_image(source_path, label="carrier image")
    if current_source.input_sha256 != loaded_source.input_sha256:
        raise WatermarkError("carrier image changed before derivative commit")
    _publish_bytes_exclusive(
        destination_path,
        output_bytes,
        label="watermarked image output",
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "local_verified",
        "algorithm": ALGORITHM,
        "local_verified": True,
        "pre_sha256": loaded_source.input_sha256,
        "post_sha256": post_sha256,
        "psnr_db": round(psnr_db, 4),
        "psnr_threshold_db": MIN_PSNR_DB,
        "payload_fingerprint": expected_fingerprint,
        "version": PAYLOAD_VERSION,
        "purpose": PAYLOAD_PURPOSE,
        "key_epoch": key_epoch,
        "carrier": assessment,
        "detection": detection,
        "transport_simulation": transport_simulation,
    }
    if include_private_record:
        report["private_record"] = {
            "wm_id": identifier.hex(),
            "payload_fingerprint": expected_fingerprint,
            "version": PAYLOAD_VERSION,
            "purpose": PAYLOAD_PURPOSE,
            "key_epoch": key_epoch,
        }
    public_report = _strict_public_report(report)
    if include_private_record:
        public_report["private_record"] = _strict_private_record(report["private_record"])
    return public_report


def _write_json(path: Path, value: dict[str, Any], *, private: bool = False) -> None:
    if private:
        path = _validated_private_record_path(path)
    try:
        encoded = (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WatermarkError("JSON output contains an unsupported value") from exc
    _publish_bytes_exclusive(
        path,
        encoded,
        label="private record" if private else "public report",
        mode=0o600,
    )


_STRING = (str,)
_OPTIONAL_STRING = (str, type(None))
_INTEGER = (int,)
_OPTIONAL_INTEGER = (int, type(None))
_BOOLEAN = (bool,)
_FLOAT = (float,)
_OPTIONAL_FLOAT = (float, type(None))

_DETECTION_PUBLIC_SCHEMA: dict[str, Any] = {
    "schema_version": _INTEGER,
    "status": _STRING,
    "algorithm": _STRING,
    "detected": _BOOLEAN,
    "authenticated": _BOOLEAN,
    "payload_fingerprint": _OPTIONAL_STRING,
    "version": _OPTIONAL_INTEGER,
    "purpose": _OPTIONAL_INTEGER,
    "key_epoch": _OPTIONAL_INTEGER,
    "repeat_vote_agreement": _FLOAT,
    "mean_abs_margin": _FLOAT,
    "input_sha256": _STRING,
    "input_bytes": _INTEGER,
    "image": {
        "width": _INTEGER,
        "height": _INTEGER,
        "mode": _STRING,
        "format": _OPTIONAL_STRING,
    },
}

_CARRIER_PUBLIC_SCHEMA: dict[str, Any] = {
    "eligible": _BOOLEAN,
    "reason_codes": [_STRING],
    "width": _OPTIONAL_INTEGER,
    "height": _OPTIONAL_INTEGER,
    "mode": _OPTIONAL_STRING,
    "format": _OPTIONAL_STRING,
    "opaque": _BOOLEAN,
    "texture_stddev": _OPTIONAL_FLOAT,
    "detail_rms": _OPTIONAL_FLOAT,
    "input_sha256": _OPTIONAL_STRING,
    "input_bytes": _OPTIONAL_INTEGER,
    "reason": _OPTIONAL_STRING,
}

_TRANSPORT_SIMULATION_PUBLIC_SCHEMA: dict[str, Any] = {
    "profile": _STRING,
    "status": _STRING,
    "payload_authenticated": _BOOLEAN,
    "payload_fingerprint": _OPTIONAL_STRING,
    "width": _INTEGER,
    "height": _INTEGER,
    "jpeg_quality": _INTEGER,
    "simulated_sha256": _STRING,
    "simulated_bytes": _INTEGER,
    "repeat_vote_agreement": _FLOAT,
}

_EMBED_PUBLIC_SCHEMA: dict[str, Any] = {
    "schema_version": _INTEGER,
    "status": _STRING,
    "algorithm": _STRING,
    "local_verified": _BOOLEAN,
    "pre_sha256": _STRING,
    "post_sha256": _STRING,
    "psnr_db": _FLOAT,
    "psnr_threshold_db": _FLOAT,
    "payload_fingerprint": _STRING,
    "version": _INTEGER,
    "purpose": _INTEGER,
    "key_epoch": _INTEGER,
    "carrier": _CARRIER_PUBLIC_SCHEMA,
    "detection": _DETECTION_PUBLIC_SCHEMA,
    "transport_simulation": _TRANSPORT_SIMULATION_PUBLIC_SCHEMA,
}

_PRIVATE_RECORD_SCHEMA: dict[str, Any] = {
    "wm_id": _STRING,
    "payload_fingerprint": _STRING,
    "version": _INTEGER,
    "purpose": _INTEGER,
    "key_epoch": _INTEGER,
}


def _copy_allowlisted(value: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field, nested_schema in schema.items():
        if field not in value:
            raise WatermarkError(f"internal report is missing required field: {field}")
        item = value[field]
        if isinstance(nested_schema, dict):
            if not isinstance(item, dict):
                raise WatermarkError(f"internal report field must be an object: {field}")
            output[field] = _copy_allowlisted(item, nested_schema)
        elif isinstance(nested_schema, list):
            if not isinstance(item, list) or len(nested_schema) != 1:
                raise WatermarkError(f"internal report field must be a list: {field}")
            element_schema = nested_schema[0]
            copied_items = []
            for element in item:
                if not isinstance(element_schema, tuple) or type(element) not in element_schema:
                    raise WatermarkError(f"internal report list has invalid values: {field}")
                _require_finite_json_numbers(element, field=field)
                copied_items.append(element)
            output[field] = copied_items
        else:
            if not isinstance(nested_schema, tuple) or type(item) not in nested_schema:
                raise WatermarkError(f"internal report field has invalid type: {field}")
            _require_finite_json_numbers(item, field=field)
            output[field] = item
    return output


def _require_finite_json_numbers(value: Any, *, field: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise WatermarkError(f"report field is not a finite JSON number: {field}")
    if isinstance(value, list):
        for item in value:
            _require_finite_json_numbers(item, field=field)
    elif isinstance(value, dict):
        for nested_field, item in value.items():
            _require_finite_json_numbers(item, field=f"{field}.{nested_field}")


def _strict_public_report(report: dict[str, Any]) -> dict[str, Any]:
    schema = _EMBED_PUBLIC_SCHEMA if report.get("status") == "local_verified" else _DETECTION_PUBLIC_SCHEMA
    return _copy_allowlisted(report, schema)


def _strict_private_record(record: dict[str, Any]) -> dict[str, Any]:
    return _copy_allowlisted(record, _PRIVATE_RECORD_SCHEMA)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Embed or authenticate compact watermark payloads")
    subparsers = parser.add_subparsers(dest="command", required=True)

    embed = subparsers.add_parser("embed", help="create a new watermarked PNG derivative")
    embed.add_argument("input", type=Path)
    embed.add_argument("output", type=Path)
    embed.add_argument("--key-epoch", type=int, default=1)
    embed.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    embed.add_argument("--report", type=Path, help="write the public JSON report")
    embed.add_argument(
        "--private-record",
        type=Path,
        help=(
            "write raw wm_id as mode-0600 JSON under the non-Git directory "
            f"configured by {PRIVATE_ROOT_ENV}"
        ),
    )

    detect = subparsers.add_parser("detect", help="authenticate a payload in a transport image")
    detect.add_argument("input", type=Path)
    detect.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    detect.add_argument("--report", type=Path, help="write the public JSON report")
    detect.add_argument(
        "--private-record",
        type=Path,
        help=(
            "write recovered raw wm_id as mode-0600 JSON under the non-Git directory "
            f"configured by {PRIVATE_ROOT_ENV}"
        ),
    )
    return parser


def _path_is_within_git(path: Path) -> bool:
    current = path if path.is_dir() else path.parent
    for candidate in (current, *current.parents):
        if os.path.lexists(candidate / ".git"):
            return True
        if (
            (candidate / "HEAD").is_file()
            and (candidate / "objects").is_dir()
            and (candidate / "refs").exists()
        ):
            return True
    return False


def _validated_private_record_path(path: Path) -> Path:
    configured_root = os.environ.get(PRIVATE_ROOT_ENV)
    if not configured_root:
        raise WatermarkError(
            f"--private-record requires environment variable {PRIVATE_ROOT_ENV}"
        )
    try:
        private_root = Path(configured_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WatermarkError("configured private-record root is not accessible") from exc
    if not private_root.is_dir():
        raise WatermarkError("configured private-record root must be a directory")
    if _path_is_within_git(private_root):
        raise WatermarkError("configured private-record root must be outside every Git repository")
    try:
        target_parent = path.parent.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WatermarkError("private-record parent directory must already exist") from exc
    target = target_parent / path.name
    try:
        target.relative_to(private_root)
    except ValueError as exc:
        raise WatermarkError("private-record path must remain inside the configured private root") from exc
    if _path_is_within_git(target_parent):
        raise WatermarkError("private-record path must be outside every Git repository")
    _require_new_path(target, label="private record")
    return target


def _validate_cli_paths(arguments: argparse.Namespace) -> None:
    if arguments.private_record is not None:
        arguments.private_record = _validated_private_record_path(arguments.private_record)
    named_paths: list[tuple[str, Path]] = [("input", arguments.input)]
    if arguments.command == "embed":
        named_paths.append(("output", arguments.output))
        _require_new_path(arguments.output, label="watermarked image output")
    if arguments.report is not None:
        named_paths.append(("report", arguments.report))
        _require_new_path(arguments.report, label="public report")
    if arguments.private_record is not None:
        named_paths.append(("private_record", arguments.private_record))
    resolved: dict[Path, str] = {}
    for label, path in named_paths:
        try:
            normalized = path.resolve()
        except (OSError, RuntimeError) as exc:
            raise WatermarkError(f"{label} path cannot be resolved safely") from exc
        if normalized in resolved:
            raise WatermarkError(f"{label} path must differ from {resolved[normalized]} path")
        resolved[normalized] = label


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        _validate_cli_paths(arguments)
        if arguments.command == "embed":
            report = embed_watermark(
                arguments.input,
                arguments.output,
                key=None,
                key_env=arguments.key_env,
                key_epoch=arguments.key_epoch,
                include_private_record=arguments.private_record is not None,
            )
        else:
            report = detect_watermark(
                arguments.input,
                key=None,
                key_env=arguments.key_env,
                include_private_record=arguments.private_record is not None,
            )
        if arguments.private_record is not None:
            private_record = report.get("private_record")
            if private_record is None:
                raise WatermarkError("no authenticated private record was recovered")
            _write_json(
                arguments.private_record,
                _strict_private_record(private_record),
                private=True,
            )
        public_report = _strict_public_report(report)
        if arguments.report is not None:
            _write_json(arguments.report, public_report)
        rendered = json.dumps(
            public_report,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    except WatermarkError as exc:
        print(
            json.dumps(
                {"status": "error", "error": str(exc)},
                ensure_ascii=False,
                allow_nan=False,
            ),
            file=sys.stderr,
        )
        return 2

    print(rendered)
    return 0 if public_report.get("status") != "not_detected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
