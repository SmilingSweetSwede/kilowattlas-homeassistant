---
title: Kilowattlas
description: Share the power readings of your Energy dashboard with the Kilowattlas map.
ha_category:
  - Energy
ha_release: "2026.12"
ha_iot_class: Calculated
ha_config_flow: true
ha_codeowners:
  - '@SmilingSweetSwede'
ha_domain: kilowattlas
ha_integration_type: service
ha_quality_scale: bronze
ha_platforms:
  - diagnostics
  - sensor
---

The **Kilowattlas** {% term integration %} shares the power readings of your [Energy dashboard](/docs/energy/) with [Kilowattlas](https://kilowattlas.com), a public live map of home energy. It reads the power sensors you already configured for the Energy dashboard and sends each reading the moment it is measured.

## Prerequisites

- A Kilowattlas account. Sign in at [kilowattlas.com](https://kilowattlas.com).
- Power sensors in the Energy dashboard: the power fields of your grid, solar panels, battery, home or individual devices. If you do not use the Energy dashboard, you can enter the same fields during setup instead.

During setup you are asked to agree to what is shared. Solar and battery are shown publicly on the map at about 100 m precision, without any personal identifier. Grid, home and individual device power are visible only to you. Each channel can be set to public, only you, or off on kilowattlas.com.

{% include integrations/config_flow.md %}

Home Assistant shows a code and a link; you sign in on kilowattlas.com and approve, and the setup continues by itself. It then lists the power sensors of your Energy dashboard; untick any you do not want to share.

## Configuration options

To change what is shared, open the integration and select **Configure**. You can untick sensors of the Energy dashboard, or enter sensors in the integration instead of the Energy dashboard. Sensors you add to the Energy dashboard later are shared automatically.

## How the Energy dashboard maps to Kilowattlas

| Energy dashboard | Kilowattlas |
|---|---|
| Grid power (positive when importing) | Grid, visible only to you |
| Solar power | Production |
| Battery power (positive when discharging), state of charge, capacity | Battery |
| Home power | Consumption, visible only to you |
| Individual device power | One channel per device, visible only to you |

Inverted sensors and separate import and export sensors are handled by the Energy dashboard's power settings.

## Data updates

The integration is push-based. It subscribes to every write of the shared sensors, including writes that repeat the previous value, and sends each one immediately. It never polls and never averages. Readings that cannot be sent are read back from the {% term recorder %} once Kilowattlas is reachable again, for up to 10 days.

## Supported functionality

### Diagnostic sensors

- **Sharing status**: `Connected`, `Connection error, retrying`, or `Disconnected, access revoked`.
- **Shared channels**: how many sensors are shared.
- **Last sent**, **Queued readings**, **Rejected readings in last batch**.
- **Measured sensor interval** and **Unusable readings** (disabled by default).

The device's **Visit** link opens the Kilowattlas map centred on your home.

## Repairs

- **Kilowattlas has nothing to share**: no power sensor is set up in the Energy dashboard.
- **Share from your Energy dashboard**: shown when you entered sensors in the integration and the Energy dashboard now has power sensors. Confirming switches to the Energy dashboard and keeps your history.

## Known limitations

- Only power sensors are shared; energy (kWh) statistics are not.
- A sensor without a unit, or with a unit that is not a power unit, is counted as unusable and not sent.

## Troubleshooting

**Sharing status is "Connection error, retrying"**: Home Assistant cannot reach `api.kilowattlas.com`. Readings are sent from the recorder when the connection is back.

**Rejected readings in last batch is not 0**: check the sensor's unit, and that the capacity registered on kilowattlas.com is not lower than your real peak output.

## Removing the integration

This integration follows standard integration removal.

{% include integrations/remove_device_service.md %}

Removing the integration revokes the sharing link on Kilowattlas. It does not delete the history already stored; to erase it, delete the installation on kilowattlas.com.
