#!/usr/bin/env python3
"""Create a migration-only RGBA route probe derivative.

This entrypoint is deliberately separate from formal article acquisition.  It
accepts only the neutral migration probe bound into one verified migration
report, validates the create-once Browser ingestion chain, and emits lineage
that is explicitly non-registerable and non-portable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prepare_micro_cutout import (
    NATIVE_FAILURE_CODES,
    CutoutPreparationError,
    _prepare_micro_cutout,
)


REPORT_KIND = "org-wechat-runtime-preflight-report"
PROBE_CONTRACT = "neutral-rgba-route-probe-v1"
PROBE_ACTION_ID = "run-migration-rgba-route-probe"
PROBE_ARTICLE_ID = "migration-route-probe"
PROBE_SLOT_ID = "migration.rgba-route-probe"
PROBE_ROLE = "floating-spot"
AUTHORITY_KIND = "org-wechat-migration-probe-processor-authority-v1"
DERIVATION_KIND = "org-wechat-migration-probe-cutout-derivation-v1"
FAILURE_KIND = "org-wechat-migration-probe-attempt-failure-v1"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{1,159}$")


class MigrationProbeError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def _existing_file(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise MigrationProbeError(f"{label} must be an absolute path")
    if _has_symlink(path):
        raise MigrationProbeError(f"{label} path cannot contain a symbolic link")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise MigrationProbeError(f"{label} is unavailable") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise MigrationProbeError(f"{label} must be a regular non-symlink file")
    return resolved


def _read_json_file(path: Path, label: str) -> tuple[Path, dict[str, Any]]:
    resolved = _existing_file(path, label)
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationProbeError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise MigrationProbeError(f"{label} must be a JSON object")
    return resolved, value


def _exact_case_path(template: Any, artifact_root: Path, label: str) -> Path:
    if not isinstance(template, str):
        raise MigrationProbeError(f"bound {label} template is missing")
    rendered = template.replace("{artifact_root}", str(artifact_root))
    candidate = Path(rendered)
    if not candidate.is_absolute() or str(candidate.absolute()) != rendered:
        raise MigrationProbeError(f"bound {label} path is not canonical absolute")
    try:
        candidate.relative_to(artifact_root)
    except ValueError as exc:
        raise MigrationProbeError(f"bound {label} escapes the migration artifact root") from exc
    if _has_symlink(candidate.parent):
        raise MigrationProbeError(f"bound {label} parent contains a symbolic link")
    return candidate


def _select_case(binding: dict[str, Any], attempt: int) -> tuple[dict[str, Any], dict[str, Any], Path]:
    if (
        binding.get("kind") != REPORT_KIND
        or binding.get("phase") != "migration"
        or binding.get("binding_ready") is not True
        or binding.get("phase_ready") is not False
        or binding.get("check_level") != "binding"
    ):
        raise MigrationProbeError("binding report is not an unfinalized migration binding")
    local = binding.get("local")
    if not isinstance(local, dict) or local.get("installed_registry_verified") is not True:
        raise MigrationProbeError("binding report lacks a verified installed release census")
    actions = binding.get("host_setup_actions")
    action = next(
        (
            item
            for item in actions
            if isinstance(item, dict) and item.get("id") == PROBE_ACTION_ID
        ),
        None,
    ) if isinstance(actions, list) else None
    if not isinstance(action, dict) or action.get("contract") != PROBE_CONTRACT:
        raise MigrationProbeError("binding report lacks the exact migration probe action")
    if action.get("artifact_policy") != (
        "create-once-current-binding-only;git-ignored;never-register;"
        "never-copy-to-organization-assets;never-upload-to-ardot"
    ):
        raise MigrationProbeError("binding report migration artifact policy is invalid")
    artifact_value = action.get("artifact_root")
    if not isinstance(artifact_value, str) or not Path(artifact_value).is_absolute():
        raise MigrationProbeError("binding report lacks an absolute probe artifact root")
    artifact_root = Path(artifact_value)
    if str(artifact_root.absolute()) != artifact_value or _has_symlink(artifact_root):
        raise MigrationProbeError("probe artifact root is noncanonical or symlinked")
    if not artifact_root.is_dir():
        raise MigrationProbeError("probe artifact root must already be a real directory")
    session_value = action.get("session_root")
    expected_artifact_root = (
        Path(str(session_value)) / "migration-probes" / str(binding.get("binding_nonce"))
        if isinstance(session_value, str) and Path(session_value).is_absolute()
        else None
    )
    if expected_artifact_root is None or artifact_root != expected_artifact_root:
        raise MigrationProbeError("probe artifact root is not bound to session root and nonce")
    cases = action.get("probe_cases")
    case = next(
        (
            item
            for item in cases
            if isinstance(item, dict) and item.get("attempt") == attempt
        ),
        None,
    ) if isinstance(cases, list) else None
    if not isinstance(case, dict):
        raise MigrationProbeError("attempt is not one of the bound migration probe cases")
    prompt = case.get("prompt")
    if (
        not isinstance(prompt, str)
        or case.get("prompt_sha256")
        != "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    ):
        raise MigrationProbeError("bound probe prompt digest is invalid")
    rgba = (binding.get("resolved_capabilities") or {}).get(
        "rgba_cutout_generation"
    )
    if (
        not isinstance(rgba, dict)
        or rgba.get("migration_probe_contract") != PROBE_CONTRACT
        or rgba.get("generation_route_id") != case.get("generation_route")
    ):
        raise MigrationProbeError("bound probe case does not match the resolved RGBA route")
    metadata = case.get("host_request_metadata")
    if (
        not isinstance(metadata, dict)
        or metadata.get("schema") != "org-wechat-migration-rgba-request-v1"
        or metadata.get("contract") != PROBE_CONTRACT
        or metadata.get("binding_nonce") != binding.get("binding_nonce")
        or metadata.get("binding_digest") != binding.get("binding_digest")
        or metadata.get("attempt") != attempt
        or metadata.get("generation_route") != case.get("generation_route")
        or metadata.get("prompt_sha256") != case.get("prompt_sha256")
    ):
        raise MigrationProbeError("bound request metadata is incomplete or inconsistent")
    canonical_metadata = json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if case.get("host_request_metadata_sha256") != (
        "sha256:" + hashlib.sha256(canonical_metadata).hexdigest()
    ):
        raise MigrationProbeError("bound request metadata digest is invalid")
    runtime_root = Path(__file__).resolve().parent.parent
    expected_command = [
        "python3",
        "-I",
        "-S",
        str(runtime_root / "scripts" / "secure_runner.py"),
        str(Path(__file__).resolve()),
        case.get("raw_path"),
        case.get("derived_path"),
        "--binding-report",
        "{binding_report}",
        "--ingestion-report",
        case.get("ingestion_report_path"),
        "--attempt",
        str(attempt),
        "--role",
        PROBE_ROLE,
        "--article-id",
        PROBE_ARTICLE_ID,
        "--asset-slot-id",
        PROBE_SLOT_ID,
        "--prompt-sha256",
        case.get("prompt_sha256"),
        "--generation-route",
        case.get("generation_route"),
    ]
    if attempt == 1:
        expected_command.extend(
            ["--failure-report", case.get("failure_report_path"), "--require-native-alpha"]
        )
    else:
        expected_command.extend(
            [
                "--previous-failure-report",
                "{artifact_root}/cutout-failure-attempt-1.json",
                "--key-color",
                case.get("key_color"),
            ]
        )
    expected_command.extend(["--report", case.get("derivation_report_path")])
    if case.get("processor_command") != expected_command:
        raise MigrationProbeError("bound migration processor command is invalid")
    return action, case, artifact_root


def _validate_ingestion(
    *,
    binding: dict[str, Any],
    case: dict[str, Any],
    artifact_root: Path,
    source: Path,
    report_path: Path,
) -> dict[str, Any]:
    expected_source = _exact_case_path(case.get("raw_path"), artifact_root, "raw")
    expected_report = _exact_case_path(
        case.get("ingestion_report_path"), artifact_root, "ingestion report"
    )
    source = _existing_file(source, "probe source")
    report_path, report = _read_json_file(report_path, "download ingestion report")
    if source != expected_source or report_path != expected_report:
        raise MigrationProbeError("source or ingestion report is not the selected bound case")
    bound = report.get("binding")
    trace = report.get("host_trace")
    observed = report.get("source")
    target = report.get("target")
    if (
        report.get("schema_version") != 1
        or report.get("kind") != "org-wechat-browser-download-ingestion-v1"
        or report.get("assurance") != "current-session-observed-path"
        or report.get("browser_event_attested") is not False
        or not isinstance(bound, dict)
        or bound.get("binding_nonce") != binding.get("binding_nonce")
        or bound.get("binding_digest") != binding.get("binding_digest")
        or bound.get("request_metadata_sha256")
        != case.get("host_request_metadata_sha256")
        or not isinstance(trace, dict)
        or any(
            not isinstance(trace.get(name), str)
            or not IDENTIFIER.fullmatch(str(trace.get(name)))
            for name in (
                "provider_session_id",
                "provider_request_id",
                "observed_download_id",
            )
        )
        or not isinstance(observed, dict)
        or not isinstance(target, dict)
        or target.get("path") != str(source)
        or target.get("create_once") is not True
        or target.get("sha256") != _sha256(source)
        or target.get("byte_length") != source.stat().st_size
        or observed.get("sha256") != target.get("sha256")
        or observed.get("byte_length") != target.get("byte_length")
    ):
        raise MigrationProbeError("download ingestion does not bind the exact selected source bytes")
    return {
        "path": str(report_path),
        "sha256": _sha256(report_path),
        "source_sha256": _sha256(source),
        "source_byte_length": source.stat().st_size,
        "host_trace": trace,
    }


def _recompute_native_failure(source: Path) -> str | None:
    from asset_quality import classify_native_alpha_failure

    return classify_native_alpha_failure(source)


def _validate_previous_failure(
    *,
    binding: dict[str, Any],
    action: dict[str, Any],
    artifact_root: Path,
    failure_path: Path,
) -> dict[str, Any]:
    cases = action.get("probe_cases")
    first = next(
        (item for item in cases if isinstance(item, dict) and item.get("attempt") == 1),
        None,
    ) if isinstance(cases, list) else None
    if not isinstance(first, dict):
        raise MigrationProbeError("attempt 1 is not bound")
    expected_failure = _exact_case_path(
        first.get("failure_report_path"), artifact_root, "attempt 1 failure report"
    )
    failure_path, failure = _read_json_file(failure_path, "attempt 1 failure report")
    if failure_path != expected_failure:
        raise MigrationProbeError("attempt 2 did not use the bound attempt 1 failure report")
    first_source = _exact_case_path(first.get("raw_path"), artifact_root, "attempt 1 raw")
    first_ingestion = _exact_case_path(
        first.get("ingestion_report_path"), artifact_root, "attempt 1 ingestion report"
    )
    ingestion = _validate_ingestion(
        binding=binding,
        case=first,
        artifact_root=artifact_root,
        source=first_source,
        report_path=first_ingestion,
    )
    error = failure.get("error")
    recomputed = _recompute_native_failure(first_source)
    if (
        failure.get("schema_version") != 1
        or failure.get("kind") != FAILURE_KIND
        or failure.get("status") != "allowed-native-gate-failure"
        or failure.get("attempt") != 1
        or failure.get("article_id") != PROBE_ARTICLE_ID
        or failure.get("asset_slot_id") != PROBE_SLOT_ID
        or failure.get("role") != PROBE_ROLE
        or failure.get("binding_nonce") != binding.get("binding_nonce")
        or failure.get("binding_digest") != binding.get("binding_digest")
        or failure.get("prompt_sha256") != first.get("prompt_sha256")
        or failure.get("host_request_metadata_sha256")
        != first.get("host_request_metadata_sha256")
        or failure.get("generation_route") != first.get("generation_route")
        or failure.get("source_sha256") != ingestion["source_sha256"]
        or failure.get("ingestion_report_sha256") != ingestion["sha256"]
        or failure.get("processor_script")
        != "scripts/prepare_migration_probe.py"
        or failure.get("processor_script_sha256")
        != _sha256(Path(__file__).resolve())
        or not isinstance(error, dict)
        or error.get("code") not in NATIVE_FAILURE_CODES
        or error.get("code") != recomputed
        or failure.get("create_once") is not True
        or failure.get("article_asset_authority") is not False
        or failure.get("registerable") is not False
    ):
        raise MigrationProbeError("attempt 1 failure evidence is not a real allowed native gate failure")
    return {"path": str(failure_path), "sha256": _sha256(failure_path), "error_code": recomputed}


def _write_failure(
    path: Path,
    *,
    binding: dict[str, Any],
    case: dict[str, Any],
    source: Path,
    ingestion: dict[str, Any],
    error: CutoutPreparationError,
) -> None:
    expected_code = _recompute_native_failure(source)
    if error.code not in NATIVE_FAILURE_CODES or error.code != expected_code:
        return
    if (
        not path.is_absolute()
        or _has_symlink(path.parent)
        or not path.parent.is_dir()
        or os.path.lexists(path)
    ):
        raise MigrationProbeError("attempt 1 failure report must be a new absolute non-symlink path")
    payload = {
        "schema_version": 1,
        "kind": FAILURE_KIND,
        "status": "allowed-native-gate-failure",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "attempt": 1,
        "article_id": PROBE_ARTICLE_ID,
        "asset_slot_id": PROBE_SLOT_ID,
        "role": PROBE_ROLE,
        "binding_nonce": binding.get("binding_nonce"),
        "binding_digest": binding.get("binding_digest"),
        "prompt_sha256": case.get("prompt_sha256"),
        "host_request_metadata_sha256": case.get("host_request_metadata_sha256"),
        "generation_route": case.get("generation_route"),
        "source_sha256": ingestion["source_sha256"],
        "ingestion_report_sha256": ingestion["sha256"],
        "processor_script": "scripts/prepare_migration_probe.py",
        "processor_script_sha256": _sha256(Path(__file__).resolve()),
        "error": {"code": error.code, "message": str(error)},
        "fallback_eligible": True,
        "requires_new_user_confirmation": False,
        "next_action": {
            "attempt": 2,
            "acquisition_mode": "controlled-key-fallback",
            "prompt_sha256": next(
                (
                    item.get("prompt_sha256")
                    for item in (
                        next(
                            (
                                action.get("probe_cases")
                                for action in binding.get("host_setup_actions", [])
                                if isinstance(action, dict)
                                and action.get("id") == PROBE_ACTION_ID
                            ),
                            [],
                        )
                    )
                    if isinstance(item, dict) and item.get("attempt") == 2
                ),
                None,
            ),
            "failure_report": str(path),
            "processor_command_source": "binding-report-attempt-2",
        },
        "create_once": True,
        "migration_only": True,
        "article_asset_authority": False,
        "registerable": False,
        "portable": False,
        "carry_forward": False,
    }
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)


def prepare_migration_probe(
    source_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    binding_report_path: Path,
    ingestion_report_path: Path,
    attempt: int,
    role: str,
    article_id: str,
    asset_slot_id: str,
    prompt_sha256: str,
    generation_route: str,
    failure_report_path: Path | None = None,
    previous_failure_report_path: Path | None = None,
    key_color: str | None = None,
    require_native_alpha: bool = False,
) -> dict[str, Any]:
    if (article_id, asset_slot_id, role) != (
        PROBE_ARTICLE_ID,
        PROBE_SLOT_ID,
        PROBE_ROLE,
    ):
        raise MigrationProbeError("migration processor cannot receive article asset scope")
    binding_path, binding = _read_json_file(binding_report_path, "migration binding report")
    action, case, artifact_root = _select_case(binding, attempt)
    expected = {
        "prompt_sha256": prompt_sha256,
        "generation_route": generation_route,
    }
    if any(case.get(key) != value for key, value in expected.items()):
        raise MigrationProbeError("processor request does not match the selected bound probe case")
    source = _existing_file(source_path, "probe source")
    output_expected = _exact_case_path(case.get("derived_path"), artifact_root, "derivative")
    report_expected = _exact_case_path(case.get("derivation_report_path"), artifact_root, "derivation report")
    if output_path.absolute() != output_expected or report_path.absolute() != report_expected:
        raise MigrationProbeError("processor output/report path is not the selected bound probe case")
    ingestion = _validate_ingestion(
        binding=binding,
        case=case,
        artifact_root=artifact_root,
        source=source,
        report_path=ingestion_report_path,
    )
    if attempt == 1:
        expected_failure = _exact_case_path(
            case.get("failure_report_path"), artifact_root, "attempt 1 failure report"
        )
        if failure_report_path is None or failure_report_path.absolute() != expected_failure:
            raise MigrationProbeError("attempt 1 requires its bound create-once failure report path")
        if previous_failure_report_path is not None or not require_native_alpha or key_color is not None:
            raise MigrationProbeError("attempt 1 must be the native-alpha route only")
        previous_failure = None
    elif attempt == 2:
        if failure_report_path is not None or previous_failure_report_path is None:
            raise MigrationProbeError("attempt 2 requires only the bound attempt 1 failure evidence")
        if require_native_alpha or key_color != case.get("key_color"):
            raise MigrationProbeError("attempt 2 must use the exact controlled-key fallback")
        previous_failure = _validate_previous_failure(
            binding=binding,
            action=action,
            artifact_root=artifact_root,
            failure_path=previous_failure_report_path,
        )
    else:
        raise MigrationProbeError("only migration probe attempts 1 and 2 exist")
    authority = {
        "kind": AUTHORITY_KIND,
        "validated": True,
        "migration_only": True,
        "article_asset_authority": False,
        "registerable": False,
        "portable": False,
        "carry_forward": False,
        "binding_report": {"path": str(binding_path), "sha256": _sha256(binding_path)},
        "binding_nonce": binding.get("binding_nonce"),
        "binding_digest": binding.get("binding_digest"),
        "contract": PROBE_CONTRACT,
        "attempt": attempt,
        "acquisition_mode": case.get("acquisition_mode"),
        "prompt_sha256": case.get("prompt_sha256"),
        "host_request_metadata_sha256": case.get("host_request_metadata_sha256"),
        "generation_route": case.get("generation_route"),
        "download_ingestion": ingestion,
        "source_sha256": ingestion["source_sha256"],
        "source_byte_length": ingestion["source_byte_length"],
        "previous_attempt_failure": previous_failure,
        "processor_script": "scripts/prepare_migration_probe.py",
        "processor_script_sha256": _sha256(Path(__file__).resolve()),
        "pixel_processor_script": "scripts/prepare_micro_cutout.py",
        "pixel_processor_script_sha256": _sha256(
            Path(__file__).resolve().parent / "prepare_micro_cutout.py"
        ),
    }
    try:
        return _prepare_micro_cutout(
            source,
            output_path,
            report_path,
            role=role,
            article_id=article_id,
            asset_slot_id=asset_slot_id,
            prompt_sha256=prompt_sha256,
            generation_route=generation_route,
            key_color=key_color,
            require_native_alpha=require_native_alpha,
            migration_probe_authority=authority,
        )
    except CutoutPreparationError as exc:
        if attempt == 1 and failure_report_path is not None:
            _write_failure(
                failure_report_path,
                binding=binding,
                case=case,
                source=source,
                ingestion=ingestion,
                error=exc,
            )
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--binding-report", type=Path, required=True)
    parser.add_argument("--ingestion-report", type=Path, required=True)
    parser.add_argument("--attempt", type=int, choices=(1, 2), required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--article-id", required=True)
    parser.add_argument("--asset-slot-id", required=True)
    parser.add_argument("--prompt-sha256", required=True)
    parser.add_argument("--generation-route", required=True)
    parser.add_argument("--failure-report", type=Path)
    parser.add_argument("--previous-failure-report", type=Path)
    parser.add_argument("--key-color")
    parser.add_argument("--require-native-alpha", action="store_true")
    return parser


def main() -> int:
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/prepare_migration_probe.py")
    args = _parser().parse_args()
    try:
        result = prepare_migration_probe(
            args.source,
            args.output,
            args.report,
            binding_report_path=args.binding_report,
            ingestion_report_path=args.ingestion_report,
            attempt=args.attempt,
            role=args.role,
            article_id=args.article_id,
            asset_slot_id=args.asset_slot_id,
            prompt_sha256=args.prompt_sha256,
            generation_route=args.generation_route,
            failure_report_path=args.failure_report,
            previous_failure_report_path=args.previous_failure_report,
            key_color=args.key_color,
            require_native_alpha=args.require_native_alpha,
        )
    except (OSError, MigrationProbeError, CutoutPreparationError) as exc:
        code = exc.code if isinstance(exc, CutoutPreparationError) else "migration.probe.invalid"
        response: dict[str, Any] = {
            "ok": False,
            "error_code": code,
            "error": str(exc),
        }
        if args.attempt == 1 and args.failure_report is not None:
            try:
                failure_payload = json.loads(
                    args.failure_report.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                failure_payload = None
            if (
                isinstance(failure_payload, dict)
                and failure_payload.get("kind") == FAILURE_KIND
                and failure_payload.get("fallback_eligible") is True
            ):
                response.update(
                    {
                        "fallback_eligible": True,
                        "requires_new_user_confirmation": False,
                        "failure_report": str(args.failure_report.absolute()),
                        "next_action": failure_payload.get("next_action"),
                    }
                )
        print(json.dumps(response, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.absolute()),
                "report": str(args.report.absolute()),
                "sha256": result["output"]["file_sha256"],
                "migration_only": True,
                "registerable": False,
                "portable": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
