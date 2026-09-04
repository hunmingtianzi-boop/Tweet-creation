# Installed runtime location

This image-route wrapper contains instructions, not a duplicate Python
runtime. A release installs it beside the single shared runtime:

```text
SKILLS_ROOT/
├── .org-wechat-release-manifests/RELEASE_SHA.json
├── org-wechat-studio/
│   ├── scripts/
│   ├── runtime/
│   └── references/
└── chatgpt-web-image-route/
    ├── SKILL.md
    └── references/
```

Resolve the loaded wrapper path, then use its sibling
`SKILLS_ROOT/org-wechat-studio` as the only installed runtime root. Stop if that
sibling is missing, symlinked, or differs from the create-once release manifest.
Run `org-wechat-studio/scripts/release_skills.py verify-installed` before the
first image operation. A valid release exposes exactly one top-level Skill
entrypoint per Skill ID; do not select a nested wrapper copy.

Keep the user's article/project directory as the working directory and invoke
the shared runtime by absolute path:

```bash
ORG_WECHAT_RUNTIME_ROOT=/ABSOLUTE/SKILLS_ROOT/org-wechat-studio
ORG_WECHAT_SESSION_ROOT=/ABSOLUTE/PROJECT/output/runtime/SESSION_UNIQUE

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/prepare_micro_cutout.py" \
  /ABSOLUTE/PROJECT/assets/generated/provider-original.png \
  /ABSOLUTE/PROJECT/assets/derived/micro.png \
  --report /ABSOLUTE/PROJECT/assets/derived/micro-cutout.json \
  --role floating-spot \
  --article-id article-slug \
  --asset-slot-id kit.floating-spot \
  --prompt-sha256 sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --generation-route chatgpt-web-image-route-v1 \
  --acquisition-report /ABSOLUTE/PROJECT/assets/generated/micro-acquisition-v2.json \
  --require-native-alpha
```

The example selects native-alpha. For a slot whose first source option is the
planned uniform key, replace `--require-native-alpha` with that option's exact
`--key-color '#RRGGBB'`. Never pass both, and never omit both; either raw route
must still produce the same strictly validated final derivative.

Do not `cd` into or write `output/` beneath the installed Skill. Runtime session
and ingestion artifacts must be create-once absolute paths outside the Skill
root. On macOS use canonical `/private/tmp/...`, not the `/tmp` symlink, for a
temporary artifact root.

In a source checkout, the repository root two levels above this wrapper may be
used only for an explicitly selected development run with no installed release
manifest. It must never silently replace a failed installed-byte verification.
