---
title: Kilowattlas
description: Share your rooftop solar production with the Kilowattlas public map.
ha_category:
  - Energy
ha_release: "2026.9"
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

The **Kilowattlas** {% term integration %} shares your rooftop solar production with [Kilowattlas](https://kilowattlas.com), a public live map of solar production. It reads a power sensor you already have in Home Assistant and sends each reading to Kilowattlas the moment the sensor reports it.

## Prerequisites

- A Kilowattlas account. Sign in at [kilowattlas.com](https://kilowattlas.com).
- A {% term sensor %} with device class `power` that reports your solar production in W, kW or MW, for example from your inverter or a production meter.

The service is free and the integration is open source. During setup you are asked to agree that your installation's position, capacity and live production are shown publicly on the Kilowattlas map, without any personal identifier (name, account, e-mail). Home Assistant's home position is sent once as a suggestion for where the installation is; you confirm or adjust it on the website before approving the link. Beyond the map, shared data is only used to compare your installation with similar ones. Any further use is a separate choice made on the website, never by this integration.

{% include integrations/config_flow.md %}

The setup links Home Assistant to your Kilowattlas account with a short code: Home Assistant shows the code and a link, you sign in on the website and approve, and the setup continues by itself. Then choose the power sensor to share.

## Data updates

The integration is push-based. It subscribes to state changes of the chosen power sensor and sends each reading to Kilowattlas immediately, at whatever rate the sensor updates. It never polls and never averages. Readings that cannot be sent (for example during a network outage) are queued locally, survive restarts, and are sent as soon as the connection is back.

## Supported functionality

### Sensors

- **Shared production**: the live power value being shared, in kW.
- **Sharing status**: whether readings are being accepted (`Connected`), queued because Kilowattlas is unreachable (`Connection error, retrying`), or refused because the link was revoked (`Disconnected, access revoked`).

### Diagnostic sensors

- **Last sent**: when readings were last accepted.
- **Queued readings**: readings waiting to be sent. Normally 0; a climbing number means sends are failing.
- **Rejected readings in last batch**: readings Kilowattlas refused (wrong unit, value above the registered capacity, timestamp out of range).
- **Measured sensor interval** (disabled by default): how often your sensor actually updates.
- **Unusable readings** (disabled by default): sensor states that could not be interpreted.

The device's **Visit** link opens the Kilowattlas map centred on your home.

## Reconfiguration

To change the shared sensor, open the integration and select **Reconfigure**. The link to your Kilowattlas account is kept.

If Kilowattlas stops accepting the link (for example after you deleted the installation on the website), Home Assistant asks you to re-authenticate, which approves a new link in the same way as the initial setup.

## Known limitations

- Energy sensors (kWh) are not supported; the integration needs a power sensor.
- One installation per config entry. Add the integration again to share a second installation with its own sensor.
- When a queue of unsent readings grows past 20,000 entries, the oldest readings are dropped.

## Troubleshooting

**Sharing status is "Connection error, retrying"**: Home Assistant cannot reach `api.kilowattlas.com`. Readings are queued and sent when the connection is back.

**Rejected readings in last batch is not 0**: check that the chosen sensor reports solar production (not household consumption) in W, kW or MW, and that the capacity registered on kilowattlas.com is not lower than your real peak output.

**Shared production is unavailable**: the source sensor is unavailable; the integration mirrors it.

## Removing the integration

This integration follows standard integration removal.

{% include integrations/remove_device_service.md %}

Removing the integration revokes the sharing link on Kilowattlas, so no further readings can be sent. It does not delete the production history already stored. To erase it, sign in on kilowattlas.com and delete the installation.
