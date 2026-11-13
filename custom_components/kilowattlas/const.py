"""Constants for the Kilowattlas integration."""

from __future__ import annotations

import os

DOMAIN = "kilowattlas"

# Public website (the map). Separate host from the API, which the library knows.
# KILOWATTLAS_MAP_BASE overrides it for development or self-hosting (the
# device's "Visit" link), mirroring aiokilowattlas' KILOWATTLAS_API_BASE.
MAP_BASE_URL = (
    os.environ.get("KILOWATTLAS_MAP_BASE", "").strip().rstrip("/")
    or "https://kilowattlas.com"
)

# Config entry data (set at linking, changed only by reauth).
CONF_TOKEN = "token"
CONF_SITE_ID = "site_id"

# Config entry options: which sensors are shared.
#
# CONF_SOURCE says where the channels come from:
#   SOURCE_ENERGY  - the user's Energy dashboard settings (the default)
#   SOURCE_MANUAL  - CONF_PREFERENCES below, for a home without them
CONF_SOURCE = "source"
SOURCE_ENERGY = "energy"
SOURCE_MANUAL = "manual"
# Energy-dashboard-shaped preferences (energy_sources + device_consumption,
# power fields only) entered in this integration's own flow. Same keys and
# meaning as homeassistant.components.energy.data.EnergyPreferences.
CONF_PREFERENCES = "preferences"
# Channel keys the user chose not to share. New Energy sources are shared
# unless excluded here (the owner can also switch any channel off on the web).
CONF_EXCLUDED = "excluded_channels"
# False when the user chose sensors one by one instead of "share all": a
# sensor added to the Energy dashboard later is then not shared until the user
# ticks it. CONF_KNOWN holds the channel keys the user has seen and decided
# on; with CONF_SHARE_NEW off, any other key counts as excluded. Entries
# without CONF_SHARE_NEW (set up before 1.2.0) share new sensors, as they
# were told at the time.
CONF_SHARE_NEW = "share_new"
CONF_KNOWN = "known_channels"
# Channel keys that must not follow the default naming, keyed by the power
# entity: {entity_id: [channel_key, kind]}. Keeps the history of channels
# created before 1.0.0 (ev_charger, heat_pump) on the same server channel.
CONF_KEY_OVERRIDES = "key_overrides"

# Pre-1.0.0 entry data, read only by the migration in __init__.py.
LEGACY_POWER_SENSOR = "power_sensor"
LEGACY_BATTERY_POWER_SENSOR = "battery_power_sensor"
LEGACY_GRID_POWER_SENSOR = "grid_power_sensor"
LEGACY_BATTERY_SOC_SENSOR = "battery_soc_sensor"
LEGACY_CONSUMPTION_SENSOR = "consumption_sensor"
LEGACY_EV_CHARGER_SENSOR = "ev_charger_power_sensor"
LEGACY_HEAT_PUMP_SENSOR = "heat_pump_power_sensor"
LEGACY_GRID_IMPORT_POSITIVE = "grid_import_positive"
LEGACY_BATTERY_CHARGE_POSITIVE = "battery_charge_positive"
LEGACY_KEYS = (
    LEGACY_POWER_SENSOR,
    LEGACY_BATTERY_POWER_SENSOR,
    LEGACY_GRID_POWER_SENSOR,
    LEGACY_BATTERY_SOC_SENSOR,
    LEGACY_CONSUMPTION_SENSOR,
    LEGACY_EV_CHARGER_SENSOR,
    LEGACY_HEAT_PUMP_SENSOR,
    LEGACY_GRID_IMPORT_POSITIVE,
    LEGACY_BATTERY_CHARGE_POSITIVE,
)
# Server channels created before 1.0.0 for the two fixed load kinds.
LEGACY_CHANNEL_EV_CHARGER = "ev_charger"
LEGACY_CHANNEL_HEAT_PUMP = "heat_pump"

# Storage (HA Store).
#   v1/v2 held completed slot means keyed by timestamp.
#   v3 held a raw-sample retry queue.
#   v4 holds per-channel cursors; the recorder is the buffer (coordinator.py).
#      A v3 queue is carried over and sent once.
STORAGE_VERSION = 4
STORAGE_KEY = "kilowattlas_buffer"

# Repair issues.
ISSUE_USE_ENERGY = "use_energy_settings"
ISSUE_NO_CHANNELS = "no_channels"

# Status codes the coordinator publishes (translated by the enum sensor).
# Sent whenever the sharing state changed, for whoever shows it.
SIGNAL_STATUS_UPDATED = f"{DOMAIN}_status_updated"

STATUS_STARTING = "starting"
STATUS_CONNECTED = "connected"
STATUS_RETRYING = "retrying"
STATUS_REVOKED = "revoked"
STATUSES = [STATUS_STARTING, STATUS_CONNECTED, STATUS_RETRYING, STATUS_REVOKED]
