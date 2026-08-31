#!/usr/bin/env python3
"""CLI wrapper for the fail-closed Ardot-to-WeChat transport validator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/validate_transport_fidelity.py")

from transport_fidelity import validate_transport_fidelity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path, help="frozen handoff manifest JSON")
    parser.add_argument("--html", type=Path, help="optional compiled WeChat HTML")
    parser.add_argument("--intended-html", type=Path, help="intended final HTML path bound by the live host receipt")
    parser.add_argument("--live-root-export", type=Path, help="fresh host-owned Ardot current-root export")
    parser.add_argument("--live-root-receipt", type=Path, help="short-lived host-signed live-read receipt")
    parser.add_argument("--require-live-root", action="store_true")
    parser.add_argument("--compile-report", type=Path, help="hash-bound compile report")
    parser.add_argument("--require-compile-report", action="store_true")
    parser.add_argument("--readback", type=Path, help="optional saved-draft readback JSON")
    parser.add_argument("--readback-receipt", type=Path, help="host-signed saved-draft readback receipt")
    parser.add_argument("--require-readback", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = validate_transport_fidelity(
            args.handoff,
            html_path=args.html,
            intended_html_path=args.intended_html,
            live_root_path=args.live_root_export,
            live_receipt_path=args.live_root_receipt,
            require_live_root=args.require_live_root,
            compile_report_path=args.compile_report,
            require_compile_report=args.require_compile_report,
            readback_path=args.readback,
            readback_receipt_path=args.readback_receipt,
            require_readback=args.require_readback,
        )
    except ValueError as exc:
        report = {"ok": False, "errors": [{"code": "transport.mapping", "message": str(exc)}]}
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
