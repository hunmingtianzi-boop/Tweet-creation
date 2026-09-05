#!/usr/bin/env python3
"""Validate the narrow, evidence-backed interaction subset used for WeChat drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/wechat_interaction_policy.py")

try:
    from safe_paths import (
        SafePathError,
        existing_regular_file,
        new_file_path,
        write_text_create_once,
    )
except ImportError:  # package import in repository tests
    from .safe_paths import (  # type: ignore
        SafePathError,
        existing_regular_file,
        new_file_path,
        write_text_create_once,
    )


POLICY_VERSION = "wechat-svg-smil-self-v1"
MOBILE_PROFILE_SOURCE = "wechat-host-mobile-compatibility-profile-v2"
MOBILE_PROFILE_MAX_TTL_SECONDS = 24 * 60 * 60
SVG_SELF_INTERACTION = "svg-smil-self"
CSS_SWIPE_INTERACTION = "horizontal-swipe"
ALLOWED_INTERACTIONS = {SVG_SELF_INTERACTION, CSS_SWIPE_INTERACTION}
FORBIDDEN_TAGS = {
    "script",
    "style",
    "details",
    "summary",
    "iframe",
    "form",
    "link",
    "foreignobject",
    "object",
    "embed",
}
SUPPORTED_SMIL_TAGS = {"set", "animatetransform"}
KNOWN_SMIL_TAGS = SUPPORTED_SMIL_TAGS | {
    "animate",
    "animatemotion",
    "animatecolor",
    "mpath",
}
EVENT_ATTRIBUTE = re.compile(r"^on[a-z]+$", re.I)
SVG_FRAGMENT_REFERENCE = re.compile(r"(?:^#|url\(\s*#)", re.I)
JAVASCRIPT_URI = re.compile(r"^\s*javascript\s*:", re.I)
UNSAFE_INLINE_STYLE = re.compile(
    r"(?:javascript\s*:|expression\s*\(|behavior\s*:|-moz-binding)",
    re.I,
)
SHA256_VALUE = re.compile(r"^sha256:[0-9a-f]{64}$")
PLAIN_SHA256 = re.compile(r"^[0-9a-f]{64}$")
WECHAT_SVG_IMAGE = re.compile(r"^https?://mmbiz\.qpic\.cn/", re.I)
UPLOAD_PLACEHOLDER = re.compile(r"^wechat-asset://[A-Za-z0-9._:-]{1,160}$")
SMIL_SIGNATURE_ATTRS = (
    "attributename",
    "type",
    "values",
    "from",
    "to",
    "by",
    "dur",
    "repeatcount",
    "begin",
    "fill",
)
RUNTIME_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CurrentSessionMobileChallenge:
    """Exact mobile evidence facts an isolated live host must re-observe."""

    profile_sha256: str
    target_account_id: str
    draft_id: str
    policy_version: str
    nonce: str
    candidate_sha256: str
    readback_sha256: str
    host_session_id: str
    device_session_ids: tuple[str, ...]
    evidence_sha256s: tuple[str, ...]


@dataclass(frozen=True)
class CurrentSessionMobileAuthorization:
    """Nonportable response returned only by an in-process trusted host."""

    profile_sha256: str
    target_account_id: str
    draft_id: str
    candidate_sha256: str
    readback_sha256: str
    host_session_id: str
    device_session_ids: tuple[str, ...]
    evidence_sha256s: tuple[str, ...]
    authorization_event_id: str
    authorized_at: str


class CurrentSessionMobileAuthority(Protocol):
    def authorize_mobile_evidence(
        self, challenge: CurrentSessionMobileChallenge
    ) -> CurrentSessionMobileAuthorization: ...


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class _TransportParser(HTMLParser):
    def __init__(self, label: str, *, allow_upload_placeholders: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.label = label
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.tags: Counter[str] = Counter()
        self.interactions: Counter[str] = Counter()
        self.fallback_keys: set[str] = set()
        self.fallback_sequence: list[str] = []
        self.fallback_hashes: dict[str, str] = {}
        self.svg_count = 0
        self.smil_count = 0
        self.self_begin_click_count = 0
        self.smil_signatures: list[str] = []
        self.swipe_cue_count = 0
        self.svg_depth = 0
        self._dynamic_stack: list[tuple[int, int]] = []
        self._dynamic_svg: list[dict[str, Any]] = []
        self.allow_upload_placeholders = allow_upload_placeholders

    def _attrs(self, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {str(key).lower(): "" if value is None else str(value) for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        attributes = self._attrs(attrs)
        self.tags[name] += 1

        if name in FORBIDDEN_TAGS:
            self.errors.append(f"{self.label}: forbidden tag <{tag}>")
        for attr_name in attributes:
            if EVENT_ATTRIBUTE.match(attr_name):
                self.errors.append(f"{self.label}: active event attribute {attr_name} is forbidden")
        if "id" in attributes:
            self.errors.append(
                f"{self.label}: id is forbidden because WeChat strips transport IDs"
            )
        for attr_name in ("href", "xlink:href", "src", "action"):
            value = attributes.get(attr_name, "")
            if value and JAVASCRIPT_URI.search(value):
                self.errors.append(f"{self.label}: javascript URI in {attr_name} is forbidden")
        if UNSAFE_INLINE_STYLE.search(attributes.get("style", "")):
            self.errors.append(f"{self.label}: active content in inline style is forbidden")

        marker = attributes.get("data-interaction")
        if marker:
            self.interactions[marker] += 1
            if marker not in ALLOWED_INTERACTIONS:
                self.errors.append(f"{self.label}: unsupported interaction marker: {marker}")
            if marker == SVG_SELF_INTERACTION and name != "svg":
                self.errors.append(
                    f"{self.label}: {SVG_SELF_INTERACTION} must be declared on its <svg> root"
                )
            if marker == SVG_SELF_INTERACTION and attributes.get("data-policy-version") != POLICY_VERSION:
                self.errors.append(
                    f"{self.label}: {SVG_SELF_INTERACTION} requires data-policy-version={POLICY_VERSION}"
                )
            if marker == CSS_SWIPE_INTERACTION:
                compact_style = re.sub(r"\s+", "", attributes.get("style", "").lower())
                if "overflow-x:auto" not in compact_style and "overflow-x:scroll" not in compact_style:
                    self.errors.append(
                        f"{self.label}: {CSS_SWIPE_INTERACTION} requires inline overflow-x:auto|scroll"
                    )

        fallback_key = attributes.get("data-fallback-key", "").strip()
        if fallback_key:
            if fallback_key in self.fallback_keys:
                self.errors.append(f"{self.label}: duplicate fallback key: {fallback_key}")
            else:
                self.fallback_keys.add(fallback_key)
                self.fallback_sequence.append(fallback_key)
            fallback_hash = attributes.get("data-fallback-hash", "").strip().lower()
            if not SHA256_VALUE.fullmatch(fallback_hash):
                self.errors.append(
                    f"{self.label}: {fallback_key} requires data-fallback-hash=sha256:<64 hex>"
                )
            elif (
                fallback_key in self.fallback_hashes
                and self.fallback_hashes[fallback_key] != fallback_hash
            ):
                self.errors.append(
                    f"{self.label}: duplicate fallback key has conflicting hashes: {fallback_key}"
                )
            else:
                self.fallback_hashes[fallback_key] = fallback_hash
        if "data-swipe-cue" in attributes:
            self.swipe_cue_count += 1

        if name == "svg":
            self.svg_depth += 1
            self.svg_count += 1
            if marker == SVG_SELF_INTERACTION:
                if not fallback_key:
                    self.errors.append(
                        f"{self.label}: each {SVG_SELF_INTERACTION} SVG requires its own fallback key/hash"
                    )
                self._dynamic_svg.append({"smil": 0, "fallback_key": fallback_key})
                self._dynamic_stack.append((self.svg_depth, len(self._dynamic_svg) - 1))

        if self.svg_depth:
            for attr_name in ("href", "xlink:href"):
                value = attributes.get(attr_name, "").strip()
                if value and SVG_FRAGMENT_REFERENCE.search(value):
                    self.errors.append(
                        f"{self.label}: SVG fragment reference in {attr_name} is forbidden"
                    )
            if SVG_FRAGMENT_REFERENCE.search(attributes.get("style", "")):
                self.errors.append(f"{self.label}: CSS url(#...) references are forbidden inside SVG")
            if name == "use":
                self.errors.append(f"{self.label}: <use> is forbidden because it depends on references")
            if name == "image":
                image_href = attributes.get("href") or attributes.get("xlink:href", "")
                placeholder_ok = (
                    self.allow_upload_placeholders
                    and UPLOAD_PLACEHOLDER.fullmatch(image_href) is not None
                    and attributes.get("data-upload-asset-id")
                    == image_href.removeprefix("wechat-asset://")
                )
                if not WECHAT_SVG_IMAGE.match(image_href) and not placeholder_ok:
                    self.errors.append(
                        f"{self.label}: SVG <image> must use a WeChat-hosted mmbiz.qpic.cn URL"
                    )
            if name in KNOWN_SMIL_TAGS:
                self.smil_count += 1
                if name not in SUPPORTED_SMIL_TAGS:
                    self.errors.append(f"{self.label}: unverified SMIL tag <{tag}> is forbidden")
                begin = attributes.get("begin", "").strip().lower()
                if begin != "click":
                    self.errors.append(
                        f"{self.label}: <{tag}> must self-trigger with begin=\"click\"; got {begin or 'missing'}"
                    )
                else:
                    self.self_begin_click_count += 1
                if attributes.get("href") or attributes.get("xlink:href"):
                    self.errors.append(f"{self.label}: SMIL target references are forbidden")
                attribute_name = attributes.get("attributename", "").strip().lower()
                if name == "set":
                    if attribute_name not in {"fill", "opacity", "visibility"}:
                        self.errors.append(
                            f"{self.label}: <set> may change only fill, opacity, or visibility"
                        )
                    if not attributes.get("to"):
                        self.errors.append(f"{self.label}: <set> requires a to value")
                if name == "animatetransform":
                    if attribute_name != "transform" or attributes.get("type", "").lower() != "translate":
                        self.errors.append(
                            f"{self.label}: <animateTransform> is limited to attributeName=transform and type=translate"
                        )
                    if not any(attributes.get(field) for field in ("values", "from", "to", "by")):
                        self.errors.append(
                            f"{self.label}: <animateTransform> requires values/from/to/by"
                        )
                    if not attributes.get("dur"):
                        self.errors.append(f"{self.label}: <animateTransform> requires dur")
                    repeat_count = attributes.get("repeatcount", "").strip().lower()
                    if repeat_count and repeat_count != "1":
                        self.errors.append(
                            f"{self.label}: <animateTransform> repeatCount may only be 1"
                        )
                if not self._dynamic_stack:
                    self.errors.append(
                        f"{self.label}: SMIL must live inside a marked {SVG_SELF_INTERACTION} SVG"
                    )
                else:
                    dynamic_index = self._dynamic_stack[-1][1]
                    self._dynamic_svg[dynamic_index]["smil"] += 1
                    fallback_key = str(
                        self._dynamic_svg[dynamic_index].get("fallback_key", "")
                    )
                    signature_payload = {
                        "fallback_key": fallback_key,
                        "tag": name,
                        "attrs": {
                            attr_name: attributes.get(attr_name, "")
                            for attr_name in SMIL_SIGNATURE_ATTRS
                        },
                    }
                    signature = hashlib.sha256(
                        json.dumps(
                            signature_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                    self.smil_signatures.append(signature)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name != "svg":
            return
        if self._dynamic_stack and self._dynamic_stack[-1][0] == self.svg_depth:
            _, dynamic_index = self._dynamic_stack.pop()
            if self._dynamic_svg[dynamic_index]["smil"] == 0:
                self.errors.append(
                    f"{self.label}: marked {SVG_SELF_INTERACTION} SVG has no self-trigger SMIL element"
                )
        self.svg_depth = max(0, self.svg_depth - 1)

    def result(self) -> dict[str, Any]:
        if self.svg_depth or self._dynamic_stack:
            self.errors.append(f"{self.label}: unclosed SVG structure")
        missing_swipe_cues = self.interactions[CSS_SWIPE_INTERACTION] - self.swipe_cue_count
        if missing_swipe_cues > 0:
            self.errors.append(
                f"{self.label}: each horizontal-swipe interaction requires a visible data-swipe-cue"
            )
        return {
            "errors": list(dict.fromkeys(self.errors)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "tags": dict(sorted(self.tags.items())),
            "interactions": dict(sorted(self.interactions.items())),
            "fallback_keys": sorted(self.fallback_keys),
            "fallback_sequence": self.fallback_sequence,
            "fallback_hashes": dict(sorted(self.fallback_hashes.items())),
            "svg_count": self.svg_count,
            "smil_count": self.smil_count,
            "self_begin_click_count": self.self_begin_click_count,
            "smil_signatures": self.smil_signatures,
            "swipe_cue_count": self.swipe_cue_count,
        }


def inspect_html(
    payload: str,
    label: str,
    *,
    allow_upload_placeholders: bool = False,
) -> dict[str, Any]:
    parser = _TransportParser(
        label, allow_upload_placeholders=allow_upload_placeholders
    )
    parser.feed(payload)
    parser.close()
    return parser.result()


def _interaction_total(result: dict[str, Any]) -> int:
    return sum(int(value) for value in result["interactions"].values())


def _validate_mobile_profile(
    profile: dict[str, Any] | None,
    target_account_id: str | None,
    *,
    profile_path: Path | None = None,
    candidate_html: str | None = None,
    readback_html: str | None = None,
    current_session_authority: CurrentSessionMobileAuthority | None = None,
    allow_editor_review: bool = False,
) -> tuple[bool, list[str], str | None]:
    if profile is None:
        return False, ["mobile compatibility profile is missing"], None
    errors: list[str] = []
    canonical_profile_path: Path | None = None
    if profile_path is not None:
        try:
            canonical_profile_path = existing_regular_file(
                profile_path,
                label="mobile profile",
            )
        except SafePathError as exc:
            errors.append(str(exc))
    required_fields = {
        "schema_version",
        "source",
        "signature_algorithm",
        "assurance_scope",
        "key_id",
        "nonce",
        "policy_version",
        "status",
        "target_account_id",
        "draft_id",
        "probe_sha256",
        "readback_sha256",
        "verified_at",
        "valid_until",
        "clients",
        "host_session_id",
        "host_trace_sha256",
        "signature",
    }
    if profile.get("assurance_scope") == "current-session-editor-reviewed":
        required_fields.add("editor_review")
    if set(profile) != required_fields:
        errors.append("mobile profile has missing or unsigned extra fields")
    if profile.get("schema_version") != 2:
        errors.append("mobile profile schema_version must be 2")
    if profile.get("source") != MOBILE_PROFILE_SOURCE:
        errors.append(f"mobile profile source must be {MOBILE_PROFILE_SOURCE}")
    assurance_scope = profile.get("assurance_scope")
    if assurance_scope not in {"portable-signed", "current-session-live", "current-session-editor-reviewed"}:
        errors.append("mobile profile assurance_scope is invalid")
    if profile.get("policy_version") != POLICY_VERSION:
        errors.append(f"mobile profile policy_version must be {POLICY_VERSION}")
    if profile.get("status") != "passed":
        errors.append("mobile profile status must be passed")
    nonce = profile.get("nonce")
    if not isinstance(nonce, str) or re.fullmatch(r"[0-9a-f]{32,64}", nonce) is None:
        errors.append("mobile profile nonce must be 32-64 lowercase hex characters")
    profile_account = profile.get("target_account_id")
    if not isinstance(profile_account, str) or not profile_account:
        errors.append("mobile profile target_account_id is required")
    elif target_account_id and profile_account != target_account_id:
        errors.append("mobile profile target_account_id does not match the delivery target")
    for field in ("draft_id", "verified_at", "valid_until"):
        if not isinstance(profile.get(field), str) or not profile.get(field):
            errors.append(f"mobile profile {field} is required")
    for field in ("probe_sha256", "readback_sha256"):
        value = profile.get(field)
        if not isinstance(value, str) or not SHA256_VALUE.fullmatch(value.lower()):
            errors.append(f"mobile profile {field} must use sha256:<64 hex>")
    if candidate_html is not None:
        candidate_digest = "sha256:" + hashlib.sha256(
            candidate_html.encode("utf-8")
        ).hexdigest()
        if profile.get("probe_sha256") != candidate_digest:
            errors.append("mobile profile is not bound to these exact candidate bytes")
    if readback_html is not None:
        readback_digest = "sha256:" + hashlib.sha256(
            readback_html.encode("utf-8")
        ).hexdigest()
        if profile.get("readback_sha256") != readback_digest:
            errors.append("mobile profile is not bound to these exact readback bytes")
    parsed_times: dict[str, datetime] = {}
    for field in ("verified_at", "valid_until"):
        value = profile.get(field)
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
            parsed_times[field] = parsed.astimezone(timezone.utc)
        except ValueError:
            errors.append(
                f"mobile profile {field} must be an RFC3339 timestamp with timezone"
            )
    now = datetime.now(timezone.utc)
    if parsed_times.get("valid_until", datetime.max.replace(tzinfo=timezone.utc)) <= now:
        errors.append("mobile profile is expired")
    if (
        "verified_at" in parsed_times
        and "valid_until" in parsed_times
        and parsed_times["valid_until"] <= parsed_times["verified_at"]
    ):
        errors.append("mobile profile valid_until must be after verified_at")
    if (
        "verified_at" in parsed_times
        and "valid_until" in parsed_times
        and (
            parsed_times["valid_until"] - parsed_times["verified_at"]
        ).total_seconds()
        > MOBILE_PROFILE_MAX_TTL_SECONDS
    ):
        errors.append("mobile profile validity may not exceed 24 hours")
    if parsed_times.get("verified_at", now) > now + timedelta(seconds=30):
        errors.append("mobile profile verified_at is future-dated")
    clients = profile.get("clients")
    passed_platforms: set[str] = set()
    device_sessions: set[str] = set()
    evidence_sha256s: set[str] = set()
    if not isinstance(clients, list) or not clients:
        errors.append("mobile profile clients must be a non-empty list")
    else:
        for index, client in enumerate(clients):
            if not isinstance(client, dict):
                errors.append(f"mobile profile client {index} must be an object")
                continue
            platform = str(client.get("platform", "")).lower()
            if platform not in {"ios", "android"}:
                errors.append(f"mobile profile client {index} platform must be ios or android")
            elif client.get("result") == "passed":
                passed_platforms.add(platform)
            else:
                errors.append(f"mobile profile client {index} result must be passed")
            if not isinstance(client.get("wechat_version"), str) or not client.get(
                "wechat_version"
            ):
                errors.append(f"mobile profile client {index} wechat_version is required")
            evidence = client.get("preview_evidence")
            required_evidence = {
                "path",
                "sha256",
                "byte_length",
                "captured_at",
                "device_session_id",
            }
            if not isinstance(evidence, dict) or set(evidence) != required_evidence:
                errors.append(
                    f"mobile profile client {index} preview_evidence must be one complete host capture"
                )
            elif canonical_profile_path is None:
                errors.append(
                    f"mobile profile client {index} evidence cannot be verified without its source path"
                )
            else:
                candidate = (
                    canonical_profile_path.parent / str(evidence.get("path", ""))
                )
                try:
                    resolved = existing_regular_file(
                        candidate,
                        label=f"mobile profile client {index} evidence",
                    )
                    resolved.relative_to(canonical_profile_path.parent)
                except (OSError, SafePathError, ValueError):
                    errors.append(
                        f"mobile profile client {index} evidence path is unavailable or escapes its bundle"
                    )
                else:
                    try:
                        with Image.open(resolved) as image:
                            image.verify()
                        with Image.open(resolved) as image:
                            width, height = image.size
                            real_png = (
                                image.format == "PNG"
                                and width >= 100
                                and height >= 100
                                and width <= 8192
                                and height <= 16384
                            )
                    except (OSError, ValueError):
                        real_png = False
                    if not real_png:
                        errors.append(
                            f"mobile profile client {index} evidence must be a real bounded PNG capture"
                        )
                    else:
                        digest = "sha256:" + hashlib.sha256(
                            resolved.read_bytes()
                        ).hexdigest()
                        captured_at = evidence.get("captured_at")
                        try:
                            captured = datetime.fromisoformat(
                                str(captured_at).replace("Z", "+00:00")
                            )
                            if captured.tzinfo is None or captured.utcoffset() is None:
                                raise ValueError
                            captured = captured.astimezone(timezone.utc)
                        except ValueError:
                            captured = None
                        device_session_id = evidence.get("device_session_id")
                        if (
                            evidence.get("sha256") != digest
                            or evidence.get("byte_length") != resolved.stat().st_size
                            or captured is None
                            or captured > now + timedelta(seconds=30)
                            or (now - captured).total_seconds()
                            > MOBILE_PROFILE_MAX_TTL_SECONDS
                            or not isinstance(device_session_id, str)
                            or not device_session_id
                            or device_session_id in device_sessions
                            or digest in evidence_sha256s
                        ):
                            errors.append(
                                f"mobile profile client {index} evidence bytes or host metadata differ"
                            )
                        else:
                            device_sessions.add(device_session_id)
                            evidence_sha256s.add(digest)
    missing = {"ios", "android"} - passed_platforms
    if missing:
        errors.append(f"mobile profile lacks passed client coverage: {', '.join(sorted(missing))}")
    if assurance_scope == "portable-signed":
        if profile.get("signature_algorithm") != "ed25519":
            errors.append("portable mobile profile signature_algorithm must be ed25519")
        try:
            from transport_fidelity import (  # local import avoids module cycle
                _host_receipt_signature,
                _host_receipt_trust_material,
            )

            expected_key_id, public_key = _host_receipt_trust_material()
            signature = _host_receipt_signature(profile.get("signature"))
            signed_payload = {
                key: value for key, value in profile.items() if key != "signature"
            }
            message = json.dumps(
                signed_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if profile.get("key_id") != expected_key_id:
                errors.append("mobile profile key_id differs from the host trust root")
            else:
                public_key.verify(signature, message)
        except Exception as exc:  # cryptographic verification is fail-closed
            errors.append(f"mobile profile host signature is invalid: {exc}")
    elif assurance_scope == "current-session-editor-reviewed":
        review = profile.get("editor_review")
        if not allow_editor_review:
            errors.append("editor mobile review requires explicit acceptance for this current-session draft")
        if not isinstance(review, dict) or set(review) != {"reviewed_by", "review_event_id", "scope"} or any(not isinstance(v, str) or not v.strip() for v in review.values()) or review.get("scope") != "exact-draft-and-both-mobile-interactions":
            errors.append("editor review must identify the real reviewer and grouped confirmation event")
        if any(profile.get(k) is not None for k in ("signature_algorithm", "signature", "key_id")):
            errors.append("editor review is not host-attested or portable-signed")
    elif assurance_scope == "current-session-live":
        if profile.get("signature_algorithm") is not None or profile.get("signature") is not None or profile.get("key_id") is not None:
            errors.append("current-session mobile evidence must not claim a portable signature")
        if current_session_authority is None:
            errors.append(
                "current-session mobile evidence requires an in-process live host authority; "
                "serialized flags, session IDs and host-trace files cannot certify it"
            )
        elif not errors:
            candidate_sha256 = "sha256:" + hashlib.sha256(
                (candidate_html or "").encode("utf-8")
            ).hexdigest()
            readback_sha256 = "sha256:" + hashlib.sha256(
                (readback_html or "").encode("utf-8")
            ).hexdigest()
            challenge = CurrentSessionMobileChallenge(
                profile_sha256=_canonical_sha256(profile),
                target_account_id=str(profile.get("target_account_id")),
                draft_id=str(profile.get("draft_id")),
                policy_version=POLICY_VERSION,
                nonce=str(profile.get("nonce")),
                candidate_sha256=candidate_sha256,
                readback_sha256=readback_sha256,
                host_session_id=str(profile.get("host_session_id")),
                device_session_ids=tuple(sorted(device_sessions)),
                evidence_sha256s=tuple(sorted(evidence_sha256s)),
            )
            try:
                authorization = current_session_authority.authorize_mobile_evidence(
                    challenge
                )
                authorized_at = datetime.fromisoformat(
                    authorization.authorized_at.replace("Z", "+00:00")
                )
                if authorized_at.tzinfo is None or authorized_at.utcoffset() is None:
                    raise ValueError
                authorized_at = authorized_at.astimezone(timezone.utc)
            except Exception as exc:
                errors.append(
                    f"current-session mobile live authority failed: {exc}"
                )
            else:
                if (
                    not isinstance(authorization, CurrentSessionMobileAuthorization)
                    or authorization.profile_sha256 != challenge.profile_sha256
                    or authorization.target_account_id != challenge.target_account_id
                    or authorization.draft_id != challenge.draft_id
                    or authorization.candidate_sha256 != challenge.candidate_sha256
                    or authorization.readback_sha256 != challenge.readback_sha256
                    or authorization.host_session_id != challenge.host_session_id
                    or authorization.device_session_ids
                    != challenge.device_session_ids
                    or authorization.evidence_sha256s
                    != challenge.evidence_sha256s
                    or not authorization.authorization_event_id
                    or abs((now - authorized_at).total_seconds()) > 60
                ):
                    errors.append(
                        "current-session mobile live authority returned a mismatched or stale authorization"
                    )
    return not errors, errors, assurance_scope if not errors else None


def audit_transport(
    candidate_html: str,
    *,
    fallback_html: str | None = None,
    readback_html: str | None = None,
    mobile_profile: dict[str, Any] | None = None,
    target_account_id: str | None = None,
    allow_upload_placeholders: bool = False,
    mobile_profile_path: Path | None = None,
    current_session_mobile_authority: CurrentSessionMobileAuthority | None = None,
    allow_editor_review: bool = False,
) -> dict[str, Any]:
    candidate = inspect_html(
        candidate_html,
        "candidate",
        allow_upload_placeholders=allow_upload_placeholders,
    )
    interaction_total = _interaction_total(candidate)
    fatal_errors = list(candidate["errors"])
    warnings = list(candidate["warnings"])

    fallback: dict[str, Any] | None = None
    fallback_complete = interaction_total == 0
    if interaction_total:
        if fallback_html is None:
            fatal_errors.append("interactive candidate requires an information-equivalent static fallback")
        else:
            fallback = inspect_html(
                fallback_html,
                "fallback",
                allow_upload_placeholders=allow_upload_placeholders,
            )
            fatal_errors.extend(fallback["errors"])
            if _interaction_total(fallback):
                fatal_errors.append("static fallback must not contain interaction markers")
            missing_keys = set(candidate["fallback_keys"]) - set(fallback["fallback_keys"])
            if missing_keys:
                fatal_errors.append(
                    "static fallback is missing semantic keys: " + ", ".join(sorted(missing_keys))
                )
            mismatched_hashes = sorted(
                key
                for key, value in candidate["fallback_hashes"].items()
                if fallback["fallback_hashes"].get(key) != value
            )
            if mismatched_hashes:
                fatal_errors.append(
                    "static fallback changed semantic hashes: "
                    + ", ".join(mismatched_hashes)
                )
            order_matches = candidate["fallback_sequence"] == fallback["fallback_sequence"]
            if not order_matches:
                fatal_errors.append("static fallback changed semantic component order")
            if not candidate["fallback_keys"]:
                fatal_errors.append("interactive candidate requires data-fallback-key semantic markers")
            fallback_complete = (
                not fallback["errors"]
                and not missing_keys
                and not mismatched_hashes
                and order_matches
                and bool(candidate["fallback_keys"])
            )

    certification_errors: list[str] = []
    readback: dict[str, Any] | None = None
    readback_preserved: bool | None = None
    if interaction_total:
        if readback_html is None:
            certification_errors.append("saved-draft readback is missing")
        else:
            readback = inspect_html(readback_html, "readback")
            certification_errors.extend(readback["errors"])
            comparisons = {
                "interaction markers": readback["interactions"] == candidate["interactions"],
                "SMIL element count": readback["smil_count"] == candidate["smil_count"],
                "self begin=click count": readback["self_begin_click_count"]
                == candidate["self_begin_click_count"],
                "SMIL structure signatures": readback["smil_signatures"]
                == candidate["smil_signatures"],
                "semantic fallback keys": set(candidate["fallback_keys"]).issubset(
                    readback["fallback_keys"]
                ),
                "semantic component order": readback["fallback_sequence"]
                == candidate["fallback_sequence"],
                "semantic content hashes": all(
                    readback["fallback_hashes"].get(key) == value
                    for key, value in candidate["fallback_hashes"].items()
                ),
            }
            certification_errors.extend(
                f"saved-draft readback changed {label}"
                for label, matched in comparisons.items()
                if not matched
            )
            readback_preserved = not readback["errors"] and all(comparisons.values())

    mobile_certified = interaction_total == 0
    mobile_assurance_scope: str | None = None
    if interaction_total:
        mobile_certified, mobile_errors, mobile_assurance_scope = _validate_mobile_profile(
            mobile_profile,
            target_account_id,
            profile_path=mobile_profile_path,
            candidate_html=candidate_html,
            readback_html=readback_html,
            current_session_authority=current_session_mobile_authority,
            allow_editor_review=allow_editor_review,
        )
        certification_errors.extend(mobile_errors)

    fatal_errors = list(dict.fromkeys(fatal_errors))
    certification_errors = list(dict.fromkeys(certification_errors))
    dynamic_eligible = bool(interaction_total) and all(
        (
            not fatal_errors,
            fallback_complete,
            readback_preserved is True,
            mobile_certified,
            not certification_errors,
        )
    )
    if fatal_errors:
        status = "rejected"
        recommended_payload = "none"
    elif not interaction_total:
        status = "static"
        recommended_payload = "static"
    elif dynamic_eligible:
        status = "certified"
        recommended_payload = "dynamic"
    else:
        status = "candidate"
        recommended_payload = "static-fallback"

    return {
        "policy_version": POLICY_VERSION,
        "ok": not fatal_errors,
        "status": status,
        "dynamic_eligible": dynamic_eligible,
        "recommended_payload": recommended_payload,
        "candidate": candidate,
        "fallback": fallback,
        "readback": readback,
        "fallback_complete": fallback_complete,
        "readback_preserved": readback_preserved,
        "mobile_certified": mobile_certified,
        "mobile_assurance_scope": mobile_assurance_scope,
        "mobile_portable_verified": mobile_assurance_scope == "portable-signed",
        "mobile_host_attested": mobile_assurance_scope == "portable-signed",
        "target_account_id": target_account_id,
        "errors": fatal_errors,
        "certification_errors": certification_errors,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _read_text(path: Path | None) -> str | None:
    return path.read_text(encoding="utf-8") if path else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--fallback", type=Path)
    parser.add_argument("--readback", type=Path)
    parser.add_argument("--mobile-profile", type=Path)
    parser.add_argument("--target-account-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-certified",
        action="store_true",
        help="Exit non-zero unless the dynamic payload passed readback and iOS/Android preview evidence.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        output = (
            new_file_path(
                args.output,
                label="interaction policy report",
                forbidden_root=RUNTIME_ROOT,
            )
            if args.output is not None
            else None
        )
        candidate_path = existing_regular_file(args.candidate, label="candidate")
        fallback_path = (
            existing_regular_file(args.fallback, label="fallback")
            if args.fallback is not None
            else None
        )
        readback_path = (
            existing_regular_file(args.readback, label="readback")
            if args.readback is not None
            else None
        )
        mobile_profile_path = (
            existing_regular_file(args.mobile_profile, label="mobile profile")
            if args.mobile_profile is not None
            else None
        )
    except SafePathError as exc:
        raise SystemExit(str(exc)) from exc
    profile = (
        json.loads(mobile_profile_path.read_text(encoding="utf-8"))
        if mobile_profile_path is not None
        else None
    )
    report = audit_transport(
        candidate_path.read_text(encoding="utf-8"),
        fallback_html=_read_text(fallback_path),
        readback_html=_read_text(readback_path),
        mobile_profile=profile,
        target_account_id=args.target_account_id,
        mobile_profile_path=mobile_profile_path,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output is not None:
        try:
            write_text_create_once(
                output,
                rendered,
                label="interaction policy report",
                forbidden_root=RUNTIME_ROOT,
            )
        except SafePathError as exc:
            raise SystemExit(str(exc)) from exc
    print(rendered, end="")
    if not report["ok"] or (args.require_certified and not report["dynamic_eligible"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
