"""Local screenshot regression metrics, never capture-origin authentication.

Compare aligned, same-size renders. Do not resize away a broken viewport or
average a missing paragraph into a large unchanged background. Thresholds are
engineering tolerances, not a substitute for editorial or device review.
"""
from pathlib import Path
import hashlib
import math
from datetime import datetime, timezone, timedelta

from PIL import Image, ImageChops, ImageStat


def compare_screenshots(reference: Path, observed: Path) -> dict:
    with Image.open(reference) as first, Image.open(observed) as second:
        if first.size != second.size:
            return {"ok": False, "reason": "viewport-dimensions-differ"}
        def flatten(im):
            rgba = im.convert("RGBA")
            return Image.alpha_composite(Image.new("RGBA", im.size, "white"), rgba).convert("RGB")
        delta = ImageChops.difference(flatten(first), flatten(second))
    mean = sum(ImageStat.Stat(delta).mean) / 3 / 255
    worst = 0.0
    for y in range(0, delta.height, 32):
        for x in range(0, delta.width, 32):
            tile = delta.crop((x, y, min(x + 32, delta.width), min(y + 32, delta.height)))
            worst = max(worst, sum(ImageStat.Stat(tile).mean) / 3 / 255)
    return {
        "ok": mean <= 0.03 and worst <= 0.10,
        "mean_error": round(mean, 6),
        "worst_tile_error": round(worst, 6),
        "tile_size": 32,
        "identical_pixels": mean == 0,
        "capture_origin_verified": False,
    }


def validate_viewport_review(review, *, base, export, content_sha256, account, draft):
    """Verify real-readback measurements; JSON is not independent attestation."""
    errors = []
    if not isinstance(review, dict) or review.get("source") != "wechat-render-viewport-review-v1":
        return ["saved draft requires 320/390/430 px viewport review"]
    if (review.get("content_sha256"), review.get("target_account_ref"), review.get("draft_id")) != (content_sha256, account, draft):
        errors.append("viewport review belongs to different saved bytes/account/draft")
    expected = {n["node_id"]: n for c in export["chapters"] for n in c["visible_text_nodes"]}
    seen, events = set(), set()
    samples = review.get("samples")
    if not isinstance(samples, list):
        return errors + ["viewport samples must be an array"]
    for sample in samples:
        try:
            width = sample["width_px"]
            if type(width) is not int or width not in {320, 390, 430} or width in seen:
                raise ValueError("duplicate or unsupported viewport width")
            seen.add(width)
            event = sample["capture_event_id"]
            if not isinstance(event, str) or not event or event in events:
                raise ValueError("viewport capture requires distinct real capture events")
            events.add(event)
            captured = datetime.fromisoformat(sample["captured_at"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if captured.tzinfo is None or not now - timedelta(hours=1) <= captured <= now + timedelta(seconds=30):
                raise ValueError("viewport capture is stale or future-dated")
            from safe_paths import existing_regular_file
            path = existing_regular_file(base / sample["screenshot"]["path"], label="viewport screenshot")
            if "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != sample["screenshot"]["sha256"]:
                raise ValueError("viewport screenshot bytes changed")
            with Image.open(path) as image:
                if image.format != "PNG" or image.width != width or image.height != round(export["artboard"]["height_px"] * width / 390):
                    raise ValueError("viewport screenshot dimensions differ from complete article")
                image.verify()
            measured = sample["text_layers"]
            ids = [n["node_id"] for n in measured]
            if len(set(ids)) != len(ids) or set(ids) != set(expected):
                raise ValueError("viewport text census differs from the frozen Ardot root")
            for node in measured:
                original = expected[node["node_id"]]
                for metric, target in (("font_size_px", original["style"]["font_size_px"] * width / 390),
                                       ("letter_spacing_px", original["style"]["letter_spacing_px"] * width / 390),
                                       ("height_px", original["geometry"]["height"] * width / 390),
                                       ("width_px", original["geometry"]["width"] * width / 390)):
                    value = node[metric]
                    if type(value) not in (float, int) or not math.isfinite(value) or abs(value - target) > 0.6:
                        raise ValueError(f"{node['node_id']} {metric} did not scale with the container")
                if any(type(node[k]) not in (int, float) or not math.isfinite(node[k]) or node[k] < 0 for k in ("scroll_height_px", "scroll_width_px")):
                    raise ValueError("invalid viewport overflow measurement")
                if node["scroll_height_px"] > node["height_px"] + 1 or node["scroll_width_px"] > node["width_px"] + 1:
                    raise ValueError(f"{node['node_id']} wraps/overflows its frozen text bounds")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append(str(exc))
    if seen != {320, 390, 430}:
        errors.append("viewport review must cover 320, 390 and 430 px")
    return errors
