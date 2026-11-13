# Kilowattlas Home Assistant integration: rules for AI sessions

This repository is a custom integration distributed through the Home Assistant
Marketplace (built into Home Assistant from 2026.11; it used to be HACS). It is
reviewed by the Marketplace catalog (`hacs/default`) and Home Assistant
maintainers against their conventions, not ours. The file, the CI action and
the catalog keep their HACS names: `hacs.json`, `hacs/action`, `hacs/default`.
In text for users, say Marketplace. Read this before
changing anything.

## What ships must be source that lives here

- Everything under `custom_components/` is installed on users' systems. It
  must be plain, readable source kept in this repository. No bundles, no
  minified files, no "generated" headers, no source maps.
- Nothing here may be built from, copied from, or depend on another
  repository. The web app (`map_framework_2`) is private; a file written into
  this repository by a build in another repository is exactly what got the
  1.0.0 release sent back by the catalog reviewer. If the map and the
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

## The newest Home Assistant is the only target

The integration is written for, tested on and requires the newest Home
Assistant release (`homeassistant` in `hacs.json`, Requirements in the README).
No code paths, texts or install instructions for older versions. When a new
Home Assistant release is out: update the test harness (README, Development),
run the tests, try the setup in a real instance, then raise the minimum.

## Before a release

1. `python3 scripts/check_shipped_source.py`
2. Tests in Docker (see README, Development).
3. Review the whole repository as a catalog reviewer would, not only the diff:
   links use the current repository name, every shipped file is readable
   source, nothing references a private repository, `manifest.json` version
   is bumped.
4. Tag, publish a GitHub release marked as latest, and if the catalog PR
   (`hacs/default`) is open, update its links to the new release and action runs.
