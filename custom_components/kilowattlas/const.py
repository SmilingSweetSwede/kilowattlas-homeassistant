"""Constants for the Kilowattlas integration."""

from __future__ import annotations

DOMAIN = "kilowattlas"

# Public website (the map). Separate host from the API, which the library knows.
MAP_BASE_URL = "https://kilowattlas.com"

# Config entry keys.
CONF_CONSENT = "consent"
CONF_TOKEN = "token"
CONF_SITE_ID = "site_id"
CONF_POWER_SENSOR = "power_sensor"
# Optional extra sensors (0.5.0). Absent key = not shared, which is what every
# entry created before 0.5.0 looks like, so no entry migration is needed.
CONF_BATTERY_POWER_SENSOR = "battery_power_sensor"
CONF_GRID_POWER_SENSOR = "grid_power_sensor"
CONF_BATTERY_SOC_SENSOR = "battery_soc_sensor"
# Sign conventions of the user's sensors. Kilowattlas counts grid EXPORT and
# battery DISCHARGE as positive; a sensor that reports the opposite is inverted
# before sending. Stored only when true.
CONF_GRID_IMPORT_POSITIVE = "grid_import_positive"
CONF_BATTERY_CHARGE_POSITIVE = "battery_charge_positive"

# Server-side channel keys. Production has none: the server files a sample
# without channel_key under its "default" channel, which is what every site
# linked before 0.5.0 already has, so existing history continues unbroken.
CHANNEL_PRODUCTION = ""
CHANNEL_BATTERY = "battery"
CHANNEL_GRID = "grid"
CHANNEL_BATTERY_SOC = "battery_soc"

# Attributes of a CheckWatt battery SoC sensor that carry the battery's rated
# charge/discharge power (kW). Read, never written.
ATTR_CHARGE_PEAK_AC = "charge_peak_ac"
ATTR_DISCHARGE_PEAK_AC = "discharge_peak_ac"

# Storage (HA Store) for the offline retry queue.
#   v1/v2 held completed slot means keyed by timestamp.
#   v3 holds a raw-sample retry queue; v2 slot means found are carried into
#      legacy_measurements and flushed once. Entries may carry channel_key
#      (0.5.0); those without belong to production.
STORAGE_VERSION = 3
STORAGE_KEY = "kilowattlas_buffer"

# Status codes the coordinator publishes (translated by the enum sensor).
STATUS_STARTING = "starting"
STATUS_CONNECTED = "connected"
STATUS_RETRYING = "retrying"
STATUS_REVOKED = "revoked"
STATUSES = [STATUS_STARTING, STATUS_CONNECTED, STATUS_RETRYING, STATUS_REVOKED]
