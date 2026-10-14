# Kilowattlas · Home Assistant integration

Share your rooftop solar production with [Kilowattlas](https://kilowattlas.com),
a public live map of solar production. The integration reads your existing solar
**power** sensor and sends every reading the moment your sensor reports it. Your
inverter or meter sets the pace: readings arriving several times a second are
sent several times a second, readings arriving once a minute once a minute.
Nothing is sampled, thinned or averaged on the way. Readings that cannot be sent
right away (network outage, Home Assistant restart) are queued locally and sent
as soon as the connection is back, so nothing is lost.

> **Upgrading from 0.3.x?** Version 0.4.0 renames the integration (domain
> `kilowattlas_trace_the_sun` → `kilowattlas`) to match Home Assistant core
> conventions. Remove the old integration, update via HACS, restart, and add
> **Kilowattlas** again. The link on kilowattlas.com is re-approved in one step.

## Requirements

- A Kilowattlas account (sign in at https://kilowattlas.com).
- A Home Assistant **power** sensor reporting your solar output in W, kW or MW
  (for example from SolarEdge, Huawei, SMA, Fronius, Solis, a Shelly EM or a
  P1/HAN meter). An energy-only (kWh) sensor is **not** supported.

## Install (via HACS)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SmilingSweetSwede&repository=kilowattlas-trace-the-sun&category=integration)

1. Click the button above, or add this repository manually in HACS
   (⋮ → **Custom repositories**, category **Integration**).
2. Install **Kilowattlas** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Kilowattlas**.

## Linking

1. Read what is shared and tick the consent box.
2. Home Assistant shows a short **code** and a link to `kilowattlas.com/link`.
   Open the link, sign in and approve. Your site's position is prefilled from
   Home Assistant's home position; adjust it, add the panel capacity, approve.
   The dialog in Home Assistant continues by itself once you have approved.
3. Pick your solar power sensor. Done.

To change the sensor later: **⋮ → Reconfigure** on the integration. If
Kilowattlas ever stops accepting the link, Home Assistant asks you to re-link.

## What you get in Home Assistant

One **Kilowattlas** service device with:

- **Shared production** (kW) — the live value being shared. A proper power
  sensor, so Home Assistant draws history and keeps long-term statistics.
- **Sharing status** — Starting / Connected / Connection error, retrying /
  Disconnected, access revoked.
- Diagnostics: **Last sent**, **Queued readings**, **Rejected readings in last
  batch**, and (disabled by default) **Measured sensor interval** and
  **Unusable readings**.
- A **Visit** link on the device that opens the map centred on your home.

Example dashboard card:

```yaml
type: history-graph
title: Solar shared to Kilowattlas
hours_to_show: 24
entities:
  - entity: sensor.kilowattlas_shared_production
```

## Privacy & data sharing

- **Your production readings** (kW with timestamp) are sent to Kilowattlas,
  which stores 15-minute averages and keeps the raw readings only briefly. The
  live value and history are shown **publicly** on the map at your
  installation's location, without any personal identifier (no name, account
  or e-mail).
- **Your installation's position and capacity** are shown publicly on the map.
  Home Assistant's home position is sent during linking as a suggestion only;
  what is shown is the position you confirm on the website.
- **The service is free for you; your data is sold on.** Kilowattlas sells the
  shared production data to third parties. Electricity market participants use
  it to make forecasts and steer other production so the power system runs more
  efficiently. Service partners use it to see when an installation is not
  performing as it should and to contact you about a fault. Your data is also
  used to give you benchmarks of how your installation performs compared with
  similar ones. This is the same kind of production data that your inverter
  manufacturer's cloud most likely already collects and passes on.

## Stopping and removing

Two independent things; do both for a full stop.

**Remove the integration** (Settings → Devices & services → Kilowattlas → ⋮ →
Delete). This stops sending, removes the entities and local queue, and revokes
the sharing token on Kilowattlas (best effort: if Home Assistant is offline at
that moment, the token is disabled when you delete the installation on the
website). It does **not** delete the history already stored.

**Delete your data**: sign in on kilowattlas.com and delete your installation.
This disables the token and erases the production history, position and
capacity.

## How it works

- Subscribes to state changes of the chosen power sensor and forwards each
  reading, with its original timestamp (microsecond precision), to
  `POST /api/v1/contrib/solar`. A reading is sent as soon as it arrives;
  readings that arrive while a request is in flight go in the next request.
- Kilowattlas computes 15-minute averages on the server. The integration does
  no averaging.
- Readings that fail to send wait in a queue that survives restarts and are
  retried with backoff (10 s up to 5 min). The queue holds 20,000 readings;
  past that the oldest are dropped first.
- Slot size, retention and the server's preferred sample rate arrive with each
  response and are visible in the integration's diagnostics.

API client: [aiokilowattlas](https://github.com/SmilingSweetSwede/aiokilowattlas)
(MIT). This repository tracks the code submitted to Home Assistant core;
`scripts/sync_to_core.sh` copies it into a core checkout.

## Development

```bash
# Python 3.13 test harness in Docker (host has 3.12)
docker run --rm -v "$PWD/.venv-docker:/venv" -v "$PWD:/repo" -w /repo python:3.13 \
  bash -c "/venv/bin/pytest --cov=custom_components.kilowattlas"
python3 scripts/build_translations.py   # regenerate translations/en.json from strings.json
```
