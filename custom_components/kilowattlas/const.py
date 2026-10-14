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

# Storage (HA Store) for the offline retry queue.
#   v1/v2 held completed slot means keyed by timestamp.
#   v3 holds a raw-sample retry queue; v2 slot means found are carried into
#      legacy_measurements and flushed once.
STORAGE_VERSION = 3
STORAGE_KEY = "kilowattlas_buffer"

# Status codes the coordinator publishes (translated by the enum sensor).
STATUS_STARTING = "starting"
STATUS_CONNECTED = "connected"
STATUS_RETRYING = "retrying"
STATUS_REVOKED = "revoked"
STATUSES = [STATUS_STARTING, STATUS_CONNECTED, STATUS_RETRYING, STATUS_REVOKED]
