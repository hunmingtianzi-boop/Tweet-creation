# Examples are quarantined fixtures

Everything below `examples/` is historical compatibility or regression data. It is never an allowed visual input for a new organization, article, calibration strip, image prompt, Ardot root, or delivery handoff.

The release packager excludes this directory byte-for-byte. Source-zero checks also reject an `examples/` locator even when a profile tries to add it to an allowed root.

For a current forward test, create a fresh temporary organization with `scripts/orgs.py init`, copy only the new test materials into its `inputs/current/` directory, and run the gates documented in `references/使用说明.md`. Do not copy an example organization, screenshot, PDF, Ardot file, layout, or generated asset into that run.
