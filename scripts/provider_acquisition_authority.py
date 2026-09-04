#!/usr/bin/env python3
"""Validate formal provider-image acquisition and its assurance boundary.

The current-session path is an operational, operator/harness-trusted contract:
it binds the current runtime/provider session to canonical provider requests,
create-once download ingestion, the exact raw bytes, and the later per-asset
quality inspection.  No synthetic RGBA migration probe is required.  It is
deliberately *not* host-attested or portable.  A plain
Python callback cannot strengthen that assurance; when present it is only a
trusted-harness policy hook that may veto the exact acquisition challenge.

The portable path remains separate and stronger.  It requires both the signed
migration receipt and a protected-key Ed25519 provider receipt.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import contextvars
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


ACQUISITION_KIND = "org-wechat-provider-image-acquisition-v2"
INGESTION_KIND = "org-wechat-browser-download-ingestion-v1"
CURRENT_MIGRATION_KIND = "org-wechat-migration-current-session-report-v1"
PORTABLE_MIGRATION_KIND = "org-wechat-migration-final-report-v1"
PORTABLE_RECEIPT_KIND = "org-wechat-provider-image-host-receipt-v1"
AUTHORITY_CHALLENGE_KIND = "org-wechat-provider-image-authority-challenge-v1"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
RELEASE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{1,159}$")
MAX_RECEIPT_TTL = timedelta(minutes=10)

LiveAuthorityCallback = Callable[[dict[str, Any]], bool]
_LIVE_AUTHORITY: contextvars.ContextVar[LiveAuthorityCallback | None] = (
    contextvars.ContextVar("org_wechat_provider_live_authority", default=None)
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _no_symlink_components(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            return False
    return True


def _read_bound_file(
    value: Any,
    *,
    report_path: Path,
    label: str,
    errors: list[str],
) -> tuple[Path | None, dict[str, Any] | None]:
    if not isinstance(value, dict):
        errors.append(f"{label} binding is required")
        return None, None
    location = value.get("location")
    expected_sha = value.get("sha256")
    if not isinstance(location, str) or not location:
        errors.append(f"{label}.location is required")
        return None, None
    if not SHA256.fullmatch(str(expected_sha or "")):
        errors.append(f"{label}.sha256 is invalid")
        return None, None
    candidate = Path(location).expanduser()
    if not candidate.is_absolute():
        candidate = report_path.parent / candidate
    candidate = candidate.absolute()
    if not _no_symlink_components(candidate):
        errors.append(f"{label} path cannot contain symbolic links")
        return None, None
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file() or resolved.is_symlink():
            raise OSError("not a regular file")
        if _sha256_file(resolved) != expected_sha:
            errors.append(f"{label} SHA-256 does not match current bytes")
            return resolved, None
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is unavailable: {exc}")
        return None, None
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object")
        return resolved, None
    return resolved, payload


def _read_json_file(
    path: Path, *, label: str, errors: list[str]
) -> dict[str, Any] | None:
    if not _no_symlink_components(path):
        errors.append(f"{label} path cannot contain symbolic links")
        return None
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file() or resolved.is_symlink():
            raise OSError("not a regular file")
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is unavailable: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} must be a JSON object")
        return None
    return value


@contextlib.contextmanager
def live_provider_acquisition_authority(
    callback: LiveAuthorityCallback,
) -> Iterator[None]:
    """Install an optional trusted-harness policy hook for this context.

    This compatibility name predates the corrected trust model.  The callback
    is ordinary in-process Python and therefore is not an attestation boundary:
    returning ``True`` merely declines to veto the current-session acquisition,
    while ``False`` or an exception blocks it.  It never sets ``host_attested``
    or ``portable`` and has no effect on portable receipt verification.
    """

    if not callable(callback):
        raise TypeError("provider acquisition policy hook must be callable")
    token = _LIVE_AUTHORITY.set(callback)
    try:
        yield
    finally:
        _LIVE_AUTHORITY.reset(token)


def current_live_provider_authority() -> LiveAuthorityCallback | None:
    return _LIVE_AUTHORITY.get()


def article_request_metadata(
    *,
    binding_nonce: str,
    binding_digest: str,
    article_id: str,
    asset_slot_id: str,
    attempt_index: int,
    acquisition_mode: str,
    generation_route_id: str,
    prompt_sha256: str,
) -> dict[str, Any]:
    """Canonical metadata the adapter must bind to the provider request."""

    return {
        "schema": "org-wechat-article-image-request-v1",
        "binding_nonce": binding_nonce,
        "binding_digest": binding_digest,
        "article_id": article_id,
        "asset_slot_id": asset_slot_id,
        "attempt_index": attempt_index,
        "acquisition_mode": acquisition_mode,
        "generation_route_id": generation_route_id,
        "prompt_sha256": prompt_sha256,
    }


def _load_protected_keys(path: Path) -> dict[str, bytes]:
    # Reuse the migration trust-store protection policy: outside the repository,
    # root owned, non-symlink, and not writable by the repository process.
    from runtime_preflight import _load_migration_trust_store

    return _load_migration_trust_store(
        path, Path(__file__).resolve().parent.parent
    )


def _verify_host_signature(
    payload: dict[str, Any],
    *,
    trust_store: Path | None,
    label: str,
) -> list[str]:
    if trust_store is None:
        return [f"{label} requires a protected host trust store"]
    signature = payload.get("signature") if isinstance(payload.get("signature"), dict) else {}
    key_id = signature.get("key_id")
    encoded = signature.get("value_base64")
    if signature.get("algorithm") != "ed25519" or not isinstance(key_id, str) or not isinstance(encoded, str):
        return [f"{label} signature object is invalid"]
    try:
        keys = _load_protected_keys(trust_store)
        raw_signature = base64.b64decode(encoded, validate=True)
        if key_id not in keys:
            raise ValueError("untrusted signing key")
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        unsigned = dict(payload)
        unsigned.pop("signature", None)
        try:
            Ed25519PublicKey.from_public_bytes(keys[key_id]).verify(
                raw_signature, _canonical_bytes(unsigned)
            )
        except InvalidSignature as exc:
            raise ValueError("signature verification failed") from exc
    except (OSError, ValueError, binascii.Error) as exc:
        return [f"{label} verification failed: {exc}"]
    return []


def _verify_embedded_migration_receipt(
    migration: dict[str, Any],
    *,
    trust_store: Path | None,
    now: datetime,
) -> list[str]:
    errors: list[str] = []
    receipt = (
        migration.get("migration_host_receipt")
        if isinstance(migration.get("migration_host_receipt"), dict)
        else None
    )
    continuation = (
        migration.get("continuation")
        if isinstance(migration.get("continuation"), dict)
        else {}
    )
    if receipt is None:
        return ["portable migration result lacks its embedded signed migration_host_receipt"]
    if (
        receipt.get("schema_version") != 1
        or receipt.get("kind") != "org-wechat-migration-probe-host-receipt-v1"
    ):
        errors.append("embedded migration host receipt schema/kind is invalid")
    receipt_id = receipt.get("receipt_id")
    migration_selftest = (
        migration.get("migration_selftest")
        if isinstance(migration.get("migration_selftest"), dict)
        else {}
    )
    if (
        not isinstance(receipt_id, str)
        or continuation.get("receipt_id") != receipt_id
        or migration_selftest.get("receipt_id") != receipt_id
    ):
        errors.append("portable migration continuation does not bind the signed receipt id")
    continuation_expiry = _parse_time(continuation.get("expires_at"))
    if (
        continuation_expiry is None
        or continuation_expiry <= now
        or receipt.get("continuation_expires_at") != continuation.get("expires_at")
    ):
        errors.append("portable migration continuation is missing, mismatched, or expired")
    binding = receipt.get("binding") if isinstance(receipt.get("binding"), dict) else {}
    local = migration.get("local") if isinstance(migration.get("local"), dict) else {}
    resolved_harness = (
        migration.get("resolved_harness")
        if isinstance(migration.get("resolved_harness"), dict)
        else {}
    )
    capabilities = (
        migration.get("resolved_capabilities")
        if isinstance(migration.get("resolved_capabilities"), dict)
        else {}
    )
    rgba = (
        capabilities.get("rgba_cutout_generation")
        if isinstance(capabilities.get("rgba_cutout_generation"), dict)
        else {}
    )
    expected = {
        "binding_nonce": migration.get("binding_nonce"),
        "binding_digest": migration.get("binding_digest"),
        "installed_release_sha256": local.get("installed_release_sha256"),
        "registry_digest": local.get("registry_digest"),
        "registry_census_sha256": local.get("registry_census_sha256"),
        "adapter_sha256": resolved_harness.get("adapter_sha256"),
        "generation_route_id": rgba.get("generation_route_id"),
    }
    for field, value in expected.items():
        if binding.get(field) != value:
            errors.append(f"embedded migration receipt binding {field} does not match")
    replay = receipt.get("replay_protection") if isinstance(receipt.get("replay_protection"), dict) else {}
    host = receipt.get("host") if isinstance(receipt.get("host"), dict) else {}
    if (
        replay.get("single_use") is not True
        or replay.get("host_nonce_consumed") is not True
        or not isinstance(replay.get("host_ledger_id"), str)
    ):
        errors.append("embedded migration receipt lacks host replay protection")
    if host.get("capability") != "host.migration.finalize":
        errors.append("embedded migration receipt was not issued by host.migration.finalize")
    errors.extend(
        _verify_host_signature(
            receipt,
            trust_store=trust_store,
            label="embedded migration host receipt",
        )
    )
    return errors


def _verify_portable_receipt(
    receipt: dict[str, Any],
    challenge: dict[str, Any],
    *,
    trust_store: Path | None,
    now: datetime,
) -> list[str]:
    errors: list[str] = []
    if trust_store is None:
        return ["portable provider receipt requires a protected host trust store"]
    if receipt.get("schema_version") != 1 or receipt.get("kind") != PORTABLE_RECEIPT_KIND:
        return ["portable provider receipt schema/kind is invalid"]
    if challenge.get("migration_mode") != "portable-signed":
        errors.append(
            "portable provider receipt requires a host-finalized portable migration result"
        )
    issued = _parse_time(receipt.get("issued_at"))
    expires = _parse_time(receipt.get("expires_at"))
    if issued is None or expires is None or expires <= issued:
        errors.append("portable provider receipt timestamps are invalid")
    elif expires - issued > MAX_RECEIPT_TTL:
        errors.append("portable provider receipt TTL exceeds ten minutes")
    elif now < issued - timedelta(minutes=5) or now > expires:
        errors.append("portable provider receipt is not currently valid")
    if receipt.get("binding") != challenge:
        errors.append("portable provider receipt does not bind the exact acquisition chain")
    host = receipt.get("host") if isinstance(receipt.get("host"), dict) else {}
    if (
        host.get("capability") != "host.receipt.attest"
        or not isinstance(host.get("provider"), str)
        or not isinstance(host.get("session_id"), str)
        or not isinstance(host.get("request_id"), str)
    ):
        errors.append("portable provider receipt host identity is incomplete")
    errors.extend(
        _verify_host_signature(
            receipt,
            trust_store=trust_store,
            label="portable provider receipt",
        )
    )
    return errors


def validate_provider_acquisition_bundle(
    report_path: Path,
    source_path: Path,
    *,
    article_id: str,
    asset_slot_id: str,
    prompt_sha256: str,
    generation_route: str,
    attempts: list[dict[str, Any]],
    live_authority: LiveAuthorityCallback | None = None,
    portable_trust_store: Path | None = None,
    require_authority: bool = True,
) -> dict[str, Any]:
    """Validate runtime/ingestion bindings and, optionally, authorize them.

    ``ok`` means the requested operational gate passed.  Current-session
    acceptance is explicitly operator/harness-trusted and non-portable;
    ``authorized`` and ``host_attested`` are reserved for the independently
    signed portable path.
    """

    errors: list[str] = []
    structural_errors: list[str] = []
    report_path = report_path.expanduser().absolute()
    source_path = source_path.expanduser().resolve(strict=True)
    report = _read_json_file(report_path, label="provider acquisition report", errors=structural_errors)
    if report is None:
        return {
            "ok": False,
            "structural_ok": False,
            "operationally_accepted": False,
            "authorized": False,
            "authority_mode": "structural-only",
            "assurance": "structural-only",
            "host_attested": False,
            "portable": False,
            "errors": structural_errors,
        }
    if report.get("schema_version") != 2 or report.get("kind") != ACQUISITION_KIND:
        structural_errors.append(
            "formal article acquisition requires org-wechat-provider-image-acquisition-v2; legacy/self-authored v1 evidence is structural-only and rejected"
        )

    runtime = report.get("runtime_binding") if isinstance(report.get("runtime_binding"), dict) else {}
    adapter_path, adapter = _read_bound_file(
        runtime.get("adapter"), report_path=report_path, label="runtime adapter", errors=structural_errors
    )
    census_path, census = _read_bound_file(
        runtime.get("registry_census"), report_path=report_path, label="registry census", errors=structural_errors
    )
    migration_path, migration = _read_bound_file(
        runtime.get("migration_result"), report_path=report_path, label="migration result", errors=structural_errors
    )
    binding_nonce = migration.get("binding_nonce") if isinstance(migration, dict) else None
    binding_digest = migration.get("binding_digest") if isinstance(migration, dict) else None
    if not isinstance(binding_nonce, str) or not IDENTIFIER.fullmatch(binding_nonce):
        structural_errors.append("migration binding nonce is invalid")
    if not SHA256.fullmatch(str(binding_digest or "")):
        structural_errors.append("migration binding digest is invalid")

    adapter_sha = _sha256_file(adapter_path) if adapter_path is not None else None
    adapter_route = None
    if isinstance(adapter, dict):
        adapter_route = (
            ((adapter.get("capabilities") or {}).get("image.generate.rgba") or {}).get(
                "generation_route_id"
            )
        )
        if adapter.get("kind") != "org-wechat-runtime-adapter":
            structural_errors.append("runtime adapter kind is invalid")
        if adapter_route != generation_route:
            structural_errors.append(
                "generation route is not the adapter-declared generation_route_id"
            )
    census_sha = _sha256_file(census_path) if census_path is not None else None
    census_session = None
    census_release = None
    census_registry_digest = None
    if isinstance(census, dict):
        harness = census.get("harness") if isinstance(census.get("harness"), dict) else {}
        installed = (
            census.get("installed_release")
            if isinstance(census.get("installed_release"), dict)
            else {}
        )
        census_session = harness.get("session_id")
        census_release = installed.get("release_sha256")
        census_registry_digest = census.get("registry_digest")
        if census.get("kind") != "org-wechat-host-registry-census-v1":
            structural_errors.append("registry census kind is invalid")
        if harness.get("adapter_sha256") != adapter_sha:
            structural_errors.append("registry census does not bind the current adapter bytes")
        if not RELEASE_SHA256.fullmatch(str(census_release or "")):
            structural_errors.append("registry census lacks a verified installed release digest")
        if not SHA256.fullmatch(str(census_registry_digest or "")):
            structural_errors.append("registry census registry_digest is invalid")

    migration_sha = _sha256_file(migration_path) if migration_path is not None else None
    migration_mode = None
    provider_session = (report.get("host_trace") or {}).get("session_id")
    if isinstance(migration, dict):
        local = migration.get("local") if isinstance(migration.get("local"), dict) else {}
        resolved_harness = (
            migration.get("resolved_harness")
            if isinstance(migration.get("resolved_harness"), dict)
            else {}
        )
        capabilities = (
            migration.get("resolved_capabilities")
            if isinstance(migration.get("resolved_capabilities"), dict)
            else {}
        )
        rgba = (
            capabilities.get("rgba_cutout_generation")
            if isinstance(capabilities.get("rgba_cutout_generation"), dict)
            else {}
        )
        continuation = (
            migration.get("continuation")
            if isinstance(migration.get("continuation"), dict)
            else {}
        )
        if migration.get("kind") == CURRENT_MIGRATION_KIND:
            migration_mode = "current-session-nonportable"
            if (
                migration.get("ok") is not True
                or migration.get("operational_ready") is not True
                or migration.get("phase_ready") is not False
                or migration.get("assurance")
                != "current-session-observed-path-not-portable-signed"
                or continuation.get("scope") != "same-host-session-only"
                or continuation.get("provider_session_id") != provider_session
            ):
                structural_errors.append(
                    "current-session runtime binding is not valid for this provider session"
                )
        elif migration.get("kind") == PORTABLE_MIGRATION_KIND:
            migration_mode = "portable-signed"
            if (
                migration.get("ok") is not True
                or migration.get("phase_ready") is not True
                or migration.get("host_attestation") != "migration-host-receipt-verified"
                or not isinstance(migration.get("migration_host_receipt"), dict)
            ):
                structural_errors.append("portable migration result is not host-finalized")
        else:
            structural_errors.append("migration result kind is invalid")
        if local.get("installed_registry_verified") is not True:
            structural_errors.append("migration result lacks verified installed registry census")
        if local.get("registry_census_sha256") != census_sha:
            structural_errors.append("migration result does not bind the selected registry census")
        if local.get("installed_release_sha256") != census_release:
            structural_errors.append("migration result release digest does not match the census")
        if local.get("registry_digest") != census_registry_digest:
            structural_errors.append("migration result registry digest does not match the census")
        if resolved_harness.get("adapter_sha256") != adapter_sha:
            structural_errors.append("migration result does not bind the selected adapter bytes")
        if rgba.get("generation_route_id") != generation_route:
            structural_errors.append("migration result does not bind the requested generation route")
        for field, expected in (
            ("adapter_sha256", adapter_sha),
            ("generation_route_id", generation_route),
            ("installed_release_sha256", census_release),
            ("registry_digest", census_registry_digest),
        ):
            if continuation.get(field) != expected:
                structural_errors.append(f"migration continuation {field} does not match")

    attempt_bindings: list[dict[str, Any]] = []
    for attempt in attempts:
        index = attempt.get("attempt_index")
        mode = attempt.get("mode")
        attempt_prompt_sha256 = attempt.get("prompt_sha256")
        if not SHA256.fullmatch(str(attempt_prompt_sha256 or "")):
            structural_errors.append(
                f"acquisition attempt {index} prompt_sha256 is invalid"
            )
        expected_metadata = article_request_metadata(
            binding_nonce=str(binding_nonce),
            binding_digest=str(binding_digest),
            article_id=article_id,
            asset_slot_id=asset_slot_id,
            attempt_index=index if isinstance(index, int) else -1,
            acquisition_mode=str(mode),
            generation_route_id=generation_route,
            prompt_sha256=str(attempt_prompt_sha256),
        )
        request_metadata_sha = _canonical_sha256(expected_metadata)
        if attempt.get("request_metadata_sha256") != request_metadata_sha:
            structural_errors.append(
                f"acquisition attempt {index} request metadata is not canonical"
            )
        ingestion_path, ingestion = _read_bound_file(
            attempt.get("download_ingestion"),
            report_path=report_path,
            label=f"acquisition attempt {index} download ingestion",
            errors=structural_errors,
        )
        raw_path: Path | None = None
        raw_sha = None
        observed_id = attempt.get("observed_download_id")
        if isinstance(ingestion, dict):
            ingestion_binding = (
                ingestion.get("binding") if isinstance(ingestion.get("binding"), dict) else {}
            )
            ingestion_trace = (
                ingestion.get("host_trace") if isinstance(ingestion.get("host_trace"), dict) else {}
            )
            ingestion_source = (
                ingestion.get("source") if isinstance(ingestion.get("source"), dict) else {}
            )
            ingestion_target = (
                ingestion.get("target") if isinstance(ingestion.get("target"), dict) else {}
            )
            if (
                ingestion.get("kind") != INGESTION_KIND
                or ingestion.get("assurance") != "current-session-observed-path"
                or ingestion.get("browser_event_attested") is not False
            ):
                structural_errors.append(
                    f"acquisition attempt {index} ingestion truth boundary is invalid"
                )
            if (
                ingestion_binding.get("binding_nonce") != binding_nonce
                or ingestion_binding.get("binding_digest") != binding_digest
                or ingestion_binding.get("request_metadata_sha256") != request_metadata_sha
            ):
                structural_errors.append(
                    f"acquisition attempt {index} ingestion binding is not exact"
                )
            if (
                ingestion_trace.get("provider_session_id") != provider_session
                or ingestion_trace.get("provider_request_id")
                != attempt.get("provider_request_id")
                or ingestion_trace.get("observed_download_id") != observed_id
            ):
                structural_errors.append(
                    f"acquisition attempt {index} ingestion host trace does not match"
                )
            target_location = ingestion_target.get("path")
            if isinstance(target_location, str):
                raw_candidate = Path(target_location).expanduser().absolute()
                if _no_symlink_components(raw_candidate):
                    try:
                        raw_path = raw_candidate.resolve(strict=True)
                        raw_sha = _sha256_file(raw_path)
                    except OSError:
                        raw_path = None
            if raw_path is None:
                structural_errors.append(f"acquisition attempt {index} ingested raw file is unavailable")
            elif (
                ingestion_target.get("sha256") != raw_sha
                or ingestion_target.get("byte_length") != raw_path.stat().st_size
                or ingestion_target.get("create_once") is not True
                or ingestion_source.get("sha256") != raw_sha
                or ingestion_source.get("byte_length") != raw_path.stat().st_size
                or attempt.get("source_file_sha256") != raw_sha
            ):
                structural_errors.append(
                    f"acquisition attempt {index} ingestion does not bind the exact raw bytes"
                )
        if attempt.get("outcome") == "accepted" and raw_path is not None and raw_path != source_path:
            structural_errors.append(
                "accepted acquisition ingestion target is not the exact processor source file"
            )
        recomputed_native_failure = None
        if attempt.get("outcome") == "rejected":
            if mode != "native-alpha":
                structural_errors.append(
                    f"acquisition attempt {index} rejected outcome is not a native-alpha attempt"
                )
            if raw_path is not None:
                from asset_quality import classify_native_alpha_failure

                recomputed_native_failure = classify_native_alpha_failure(raw_path)
                if recomputed_native_failure is None:
                    structural_errors.append(
                        f"acquisition attempt {index} raw bytes do not reproduce an allowed native Alpha/pixel failure"
                    )
                elif attempt.get("failure_code") != recomputed_native_failure:
                    structural_errors.append(
                        f"acquisition attempt {index} failure_code does not match the recomputed raw-pixel failure"
                    )
        attempt_bindings.append(
            {
                "attempt_index": index,
                "mode": mode,
                "outcome": attempt.get("outcome"),
                "prompt_sha256": attempt_prompt_sha256,
                "recomputed_native_failure": recomputed_native_failure,
                "provider_request_id": attempt.get("provider_request_id"),
                "observed_download_id": observed_id,
                "request_metadata_sha256": request_metadata_sha,
                "ingestion_report_sha256": (
                    _sha256_file(ingestion_path) if ingestion_path is not None else None
                ),
                "ingestion_report_byte_length": (
                    ingestion_path.stat().st_size if ingestion_path is not None else None
                ),
                "raw_file_sha256": raw_sha,
                "raw_file_byte_length": raw_path.stat().st_size if raw_path is not None else None,
            }
        )

    # The host receipt is attached after the acquisition core exists.  Exclude
    # that one reference from the canonical core to avoid a receipt/report hash
    # cycle while still binding every provider, runtime, ingestion and raw-byte
    # field that precedes attestation.
    acquisition_core = dict(report)
    acquisition_core.pop("portable_host_receipt", None)
    challenge = {
        "schema_version": 1,
        "kind": AUTHORITY_CHALLENGE_KIND,
        "acquisition_core_sha256": _canonical_sha256(acquisition_core),
        "acquisition_core_byte_length": len(_canonical_bytes(acquisition_core)),
        "article_id": article_id,
        "asset_slot_id": asset_slot_id,
        "prompt_sha256": prompt_sha256,
        "generation_route_id": generation_route,
        "provider_session_id": provider_session,
        "host_registry_session_id": census_session,
        "binding_nonce": binding_nonce,
        "binding_digest": binding_digest,
        "adapter_sha256": adapter_sha,
        "adapter_byte_length": adapter_path.stat().st_size if adapter_path is not None else None,
        "registry_census_sha256": census_sha,
        "registry_census_byte_length": census_path.stat().st_size if census_path is not None else None,
        "installed_release_sha256": census_release,
        "registry_digest": census_registry_digest,
        "migration_result_sha256": migration_sha,
        "migration_result_byte_length": migration_path.stat().st_size if migration_path is not None else None,
        "migration_mode": migration_mode,
        "source_file_sha256": _sha256_file(source_path),
        "source_file_byte_length": source_path.stat().st_size,
        "attempts": attempt_bindings,
    }
    challenge["binding_sha256"] = _canonical_sha256(challenge)
    structural_ok = not structural_errors
    authority_mode = "structural-only"
    assurance = "structural-only"
    authorized = False
    operationally_accepted = False
    host_attested = False
    portable = False
    operator_harness_trusted = False
    policy_hook_evaluated = False
    policy_hook_allowed: bool | None = None
    portable_reference = report.get("portable_host_receipt")
    if portable_reference is not None:
        receipt_path, receipt = _read_bound_file(
            portable_reference,
            report_path=report_path,
            label="portable provider receipt",
            errors=errors,
        )
        if receipt is not None:
            migration_errors: list[str] = []
            if isinstance(migration, dict):
                migration_errors = _verify_embedded_migration_receipt(
                    migration,
                    trust_store=portable_trust_store,
                    now=datetime.now(timezone.utc),
                )
                errors.extend(migration_errors)
            receipt_errors = _verify_portable_receipt(
                receipt,
                challenge,
                trust_store=portable_trust_store,
                now=datetime.now(timezone.utc),
            )
            errors.extend(receipt_errors)
            if not migration_errors and not receipt_errors and structural_ok:
                authority_mode = "portable-signed"
                assurance = "portable-ed25519-double-signed"
                authorized = True
                operationally_accepted = True
                host_attested = True
                portable = True
    else:
        callback = live_authority or current_live_provider_authority()
        if structural_ok and migration_mode == "current-session-nonportable":
            operator_harness_trusted = True
            policy_allowed = True
            if callback is not None:
                policy_hook_evaluated = True
                try:
                    decision = callback(json.loads(json.dumps(challenge)))
                except Exception as exc:
                    policy_allowed = False
                    policy_hook_allowed = False
                    errors.append(f"provider acquisition policy hook failed: {exc}")
                else:
                    policy_hook_allowed = decision is True
                    if decision is not True:
                        policy_allowed = False
                        errors.append(
                            "provider acquisition policy hook denied the exact acquisition challenge"
                        )
            if policy_allowed:
                authority_mode = "current-session-operator-harness-trusted"
                assurance = "operator-harness-trusted-current-session"
                operationally_accepted = True

    errors = [*structural_errors, *errors]
    if require_authority and not operationally_accepted:
        errors.append(
            "provider acquisition is not operationally accepted; use a current-session runtime binding and exact create-once acquisition chain, or supply a verified portable host receipt"
        )
    return {
        "ok": structural_ok
        and (operationally_accepted or not require_authority)
        and not errors,
        "structural_ok": structural_ok,
        "operationally_accepted": operationally_accepted,
        "authorized": authorized,
        "authority_mode": authority_mode,
        "assurance": assurance,
        "host_attested": host_attested,
        "portable": portable,
        "portable_verified": portable,
        "operator_harness_trusted": operator_harness_trusted,
        "policy_hook_evaluated": policy_hook_evaluated,
        "policy_hook_allowed": policy_hook_allowed,
        "requires_live_revalidation": False,
        "requires_current_session_chain_revalidation": (
            authority_mode == "current-session-operator-harness-trusted"
        ),
        "challenge": challenge,
        "binding_sha256": challenge["binding_sha256"],
        "errors": errors,
    }
