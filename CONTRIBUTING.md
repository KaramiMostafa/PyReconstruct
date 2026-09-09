# Contributing to the customized branch

Development work for the microscopy plug-ins belongs on
`cellpose-custom-model`. Keep changes focused and test the affected workflow
before opening a pull request.

## Conventional Commits

Every commit unique to this customized branch must follow
[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).

```text
type(scope): description
```

- `type` and the optional `scope` use lowercase characters.
- Add `!` before `:` for a breaking change.
- Keep the first line concise and describe the change in the imperative mood.
- Use a `BREAKING CHANGE: ...` footer when migration details are needed.

Common types include `feat`, `fix`, `docs`, `test`, `refactor`, `perf`,
`build`, `ci`, `chore`, `style`, and `revert`.

Valid examples:

```text
feat(mapping): propagate mRNA ROIs with local DAPI motion
fix(tracking): preserve DAPI groups after renaming
docs(install): add Apple Silicon instructions
feat(api)!: change feedback record schema
```

Invalid examples:

```text
Updated tracking
Add some fixes
FEAT: new plugin
```

Enable the tracked local hook once per clone:

```bash
git config core.hooksPath .githooks
```

The GitHub Actions check runs the same validator on all customized commits and
must pass before merging. Prefer squash merging and give the squash commit a
Conventional Commit title.

## Basic checks

From an activated development environment:

```bash
python -m py_compile \
  PyReconstruct/modules/gui/main/main_window.py \
  PyReconstruct/modules/gui/main/menubar.py
python scripts/check_conventional_commits.py --range main..HEAD
```

Changes involving the connector should also run its test suite as described in
the connector repository.

## Plugin boundary

Do not import tracking engines or other algorithm implementations into the
PyReconstruct host. Add the public adapter to the connector, register its menu
descriptor in `pyrecon_connector/plugin_registry.py`, and add only the required
host dialog/view integration here. Run `tests/test_plugin_assembly.py` whenever
the registry or a plugin handler changes. See [PLUGINS.md](PLUGINS.md).
