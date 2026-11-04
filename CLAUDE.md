# Kilowattlas Home Assistant integration: rules for AI sessions

This repository is a HACS custom integration, reviewed by the HACS and Home
Assistant maintainers against their conventions, not ours. Read this before
changing anything.

## What ships must be source that lives here

- Everything under `custom_components/` is installed on users' systems. It
  must be plain, readable source kept in this repository. No bundles, no
  minified files, no "generated" headers, no source maps.
- Nothing here may be built from, copied from, or depend on another
  repository. The web app (`map_framework_2`) is private; a file written into
  this repository by a build in another repository is exactly what got the
  1.0.0 release sent back by the HACS reviewer. If the map and the
  integration must show the same thing, write it here in plain JS and keep
  the twin in the web app in step by hand, with a comment on both sides.
- `python3 scripts/check_shipped_source.py` enforces this and runs in CI.
  Run it before every release. Never weaken its rules to make something pass;
  change the something.

## Use what Home Assistant uses, not what the web app uses

- Frontend: plain custom elements (`class X extends HTMLElement`) with Home
  Assistant's theme variables (`--primary-color`, `--card-background-color`,
  `--secondary-text-color`, ...). No Svelte, React, Vue, no build step, no
  Node toolchain in this repository. The web app's stack does not carry over.
- Backend: Home Assistant's own helpers first. The Energy dashboard is the
  framework for sensors; `DataUpdateCoordinator`, `Store`, `config_flow`, `websocket_api`. Frequent
  writes go through one timer per interval (`_save_soon` in coordinator.py),
  not `Store.async_delay_save`: that one postpones the write at every call
  and never writes while readings keep coming.
  Before writing something new, check whether core already has it, and if
  core is missing something, prefer a PR upstream over a workaround here.
- Follow the Home Assistant developer docs and `hassfest` for manifest,
  translations, quality scale and config flow. When unsure what is
  conventional, look at a core integration that does the same thing.

## Before a release

1. `python3 scripts/check_shipped_source.py`
2. Tests in Docker (see README, Development).
3. Review the whole repository as a HACS reviewer would, not only the diff:
   links use the current repository name, every shipped file is readable
   source, nothing references a private repository, `manifest.json` version
   is bumped.
4. Tag, publish a GitHub release marked as latest, and if a HACS default PR
   is open, update its links to the new release and action runs.
