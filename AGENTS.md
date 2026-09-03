# Codex workflow entrypoint

The executable organization-WeChat workflow in this repository currently supports **Codex Desktop only**. Do not claim that another LLM, CLI agent, cloud harness, Linux, Windows, or Intel Mac can run the release merely because it can read the repository contracts.

Before any task that will read organization source material, create visuals, open Ardot, or deliver to WeChat:

1. Tell the user the current support boundary and the exact prerequisites for the requested phase.
2. Read `references/host-prerequisites.md` and use its phase matrix.
3. From this exact clone, run the read-only declaration below with absolute paths:

   ```bash
   python3 -I -S /ABSOLUTE/SOURCE/CHECKOUT/scripts/release_skills.py clone-check \
     --skills-root /ABSOLUTE/CODEX/SKILLS/ROOT \
     --phase full
   ```

   When the current model registry is available, append one
   `--visible-tool-id ID` for every actually visible phase tool. If the report
   says `current_task_reload_required: true`, reload or open a new Codex task
   and rerun it; repository code cannot hot-inject an MCP route.

4. Require the same-release `org-wechat-studio`, `chatgpt-web-image-route`, and `ardot-wechat-publisher` Skills. For phases that need generation, require the external `codex-with-chatgpt` Skill, built checkout, exact-workspace binding, and a logged-in ChatGPT session in the Codex built-in Browser. For phases that need design, require Ardot Remote OAuth/web login and exact file/root authority. For `delivery` or `full`, separately require the exact WeChat account session or execution-time API route.
5. Treat `clone-check` as local evidence only. It cannot prove current Browser login, Ardot/WeChat identity, exact file/root access, or authorization to write/publish. Close those conditions with the current Codex session's runtime preflight and live probes.

Do not open old articles, example layouts, prior Ardot files, or another organization's pack as visual references unless the user explicitly names a reference. Do not touch an Ardot design or WeChat draft while a required startup condition is unresolved. Repository-development tests and documentation work may proceed without those live service logins as long as they do not claim workflow execution readiness.
