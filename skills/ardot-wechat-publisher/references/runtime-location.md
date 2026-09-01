# Installed runtime location

The publisher wrapper is intentionally small. It does not carry a second copy
of the workflow Python runtime. A valid release installs these three sibling
directories under one Skill root:

```text
SKILLS_ROOT/
├── .org-wechat-release-manifests/RELEASE_SHA.json
├── org-wechat-studio/
│   ├── scripts/
│   ├── runtime/
│   └── references/
└── ardot-wechat-publisher/
    ├── SKILL.md
    └── references/
```

Resolve the loaded wrapper `SKILL.md` first. Its parent directory is the
wrapper root; the wrapper root's parent is `SKILLS_ROOT`; the only installed
runtime root is the sibling `SKILLS_ROOT/org-wechat-studio`. Stop if the sibling
is missing, is a symlink, or does not contain `scripts/secure_runner.py`,
`runtime/python-dependency-lock.json`, and `SKILL.md`.

Before any workflow command, run the sibling runtime's
`scripts/release_skills.py verify-installed` against the create-once manifest
under `SKILLS_ROOT/.org-wechat-release-manifests/`. The manifest release SHA and
all three active package byte censuses must agree. Never select a nested copy
of a wrapper; a valid release has exactly one top-level `SKILL.md` for each Skill
ID.

Keep the user's article/project directory as the shell working directory. Do
not `cd` into the installed runtime and do not create `output/` under a Skill
package. Invoke both the runner and its target by absolute path, for example:

```bash
ORG_WECHAT_RUNTIME_ROOT=/ABSOLUTE/SKILLS_ROOT/org-wechat-studio
ORG_WECHAT_SESSION_ROOT=/ABSOLUTE/PROJECT/output/runtime/SESSION_UNIQUE

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" --platform-audit
```

Every census/profile/report path must be create-once and absolute under
`ORG_WECHAT_SESSION_ROOT`, or another private path outside the installed
runtime. On macOS, use canonical `/private/tmp/...` rather than the `/tmp`
symlink when a temporary path is needed. Never write credentials or tokenized
URLs into that directory.

In a source checkout, the development runtime root is the repository root two
levels above this wrapper. That fallback is valid only when there is no
installed release manifest and the task is explicitly operating on the source
checkout; it must never silently replace a failed installed-byte verification.
