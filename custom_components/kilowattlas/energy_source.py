"""Which sensors are shared, read from the Home Assistant Energy dashboard.

The Energy dashboard is this integration's model of a home. Every channel is
one power field of the user's Energy settings
(`homeassistant.components.energy.data.EnergyPreferences`), and the value sent
is that sensor's value in the Energy dashboard's own sign convention:

    Energy dashboard field                 Kilowattlas kind     channel key
    -------------------------------------  -------------------  -----------------
    grid source  stat_rate                 grid_power           grid, grid_2 ...
        (positive = import, negative = export; data.py GridSourceType)
    solar source stat_rate                 gross_production     "", solar_2 ...
    battery      stat_rate                 battery_power        battery, ...
        (positive = discharge, negative = charge; data.py BatterySourceType)
    battery      stat_soc                  battery_soc          battery_soc, ...
    home         stat_rate                 consumption          consumption
    device_consumption[] stat_rate         device_power         device_<stat id>

For grid and battery sources the Energy dashboard resolves `power_config`
(one sensor, an inverted sensor, or two sensors) into the source's top-level
`stat_rate`, creating a transform sensor when needed (energy/data.py,
`EnergyManager._process_grid_power` and `_process_battery_power`). That
resolved `stat_rate` is what is read here, so inversion and "import minus
export" are never computed by this integration.

Homes without Energy settings enter the same fields in this integration's
options instead (`manual_preferences`). They are validated with the Energy
dashboard's own `POWER_CONFIG_SCHEMA`, and an inverted or two-sensor
`power_config` is computed by the Energy dashboard's own `EnergyPowerSensor`
(set up by sensor.py), so both paths share one model and one implementation.

Channel keys follow the Energy *slot* (the n-th grid source, the device's
energy statistic), not the sensor: swapping an inverter's sensor in the Energy
settings continues the same server-side history.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aiokilowattlas import (
    KIND_BATTERY_POWER,
    KIND_BATTERY_SOC,
    KIND_CONSUMPTION,
    KIND_DEVICE_POWER,
    KIND_GRID_POWER,
    KIND_GROSS_PRODUCTION,
)
from homeassistant.components.energy.data import (
    POWER_CONFIG_SCHEMA,
    async_get_manager,
)
from homeassistant.core import HomeAssistant, valid_entity_id

_LOGGER = logging.getLogger(__name__)

# Source types whose power the Energy dashboard can transform (power_config).
TRANSFORM_SOURCE_TYPES = ("grid", "battery")

# Server limit on channel_key length and character set.
MAX_CHANNEL_KEY_LEN = 64
_INVALID_KEY_CHARS = re.compile(r"[^A-Za-z0-9._-]")

_unknown_types_logged: set[str] = set()


@dataclass(frozen=True, slots=True)
class Channel:
    """One power field of the Energy settings, shared as one server channel."""

    key: str  # "" = the server's default channel (the first solar source)
    kind: str
    entity_id: str
    name: str | None = None  # device name from the Energy settings
    percent: bool = False  # a state of charge in %, not a power


@dataclass(frozen=True, slots=True)
class PowerTransform:
    """An inverted or two-sensor power_config in the manual preferences."""

    source_type: str  # "grid" | "battery"
    index: int  # position among the sources of that type
    config: dict[str, str]  # the power_config, as the Energy dashboard stores it


def transform_unique_id(entry_id: str, transform: PowerTransform) -> str:
    """Unique id of the transform sensor sensor.py sets up for `transform`."""
    return f"{entry_id}_{transform.source_type}_{transform.index}_power"


async def async_energy_preferences(hass: HomeAssistant) -> dict[str, Any] | None:
    """The user's Energy settings, or None if they never saved any."""
    manager = await async_get_manager(hass)
    data = manager.data
    return dict(data) if data else None


def _sources(
    prefs: Mapping[str, Any] | None, source_type: str
) -> list[Mapping[str, Any]]:
    """The Energy sources of one type, in the order the user configured them."""
    if not prefs:
        return []
    return [
        s
        for s in prefs.get("energy_sources") or []
        if isinstance(s, Mapping) and s.get("type") == source_type
    ]


def _is_entity(stat_id: Any) -> bool:
    """An entity's statistic id (a sensor), not an external statistic."""
    return isinstance(stat_id, str) and valid_entity_id(stat_id)


def device_channel_key(stat_id: str) -> str:
    """Channel key for an Energy device, from its statistic id."""
    return ("device_" + _INVALID_KEY_CHARS.sub("_", stat_id))[:MAX_CHANNEL_KEY_LEN]


def _numbered(first: str, base: str, index: int) -> str:
    return first if index == 0 else f"{base}_{index + 1}"


def resolve_channels(
    prefs: Mapping[str, Any] | None,
    overrides: Mapping[str, list[str]] | None = None,
) -> list[Channel]:
    """Every shareable power field of `prefs`, as channels.

    `prefs` is shaped like the Energy dashboard's preferences. Grid and battery
    sources are read through their top-level `stat_rate`, which the Energy
    dashboard fills from `power_config` (and `resolve_manual_preferences` does
    for manual preferences). Source types this version does not know are
    skipped, so a newer Home Assistant never breaks sharing.
    """
    overrides = overrides or {}
    channels: list[Channel] = []
    seen: set[str] = set()

    def add(
        key: str,
        kind: str,
        entity_id: Any,
        name: str | None = None,
        percent: bool = False,
    ) -> None:
        if not _is_entity(entity_id) or entity_id in seen:
            return
        seen.add(entity_id)
        if (override := overrides.get(entity_id)) and len(override) == 2:
            key, kind = override[0], override[1]
        channels.append(Channel(key, kind, entity_id, name, percent))

    for i, source in enumerate(_sources(prefs, "solar")):
        add(_numbered("", "solar", i), KIND_GROSS_PRODUCTION, source.get("stat_rate"))
    for i, source in enumerate(_sources(prefs, "grid")):
        add(_numbered("grid", "grid", i), KIND_GRID_POWER, source.get("stat_rate"))
    for i, source in enumerate(_sources(prefs, "battery")):
        add(
            _numbered("battery", "battery", i),
            KIND_BATTERY_POWER,
            source.get("stat_rate"),
        )
        add(
            _numbered("battery_soc", "battery_soc", i),
            KIND_BATTERY_SOC,
            source.get("stat_soc"),
            percent=True,
        )
    # At most one home source (energy/data.py check_type_limits).
    for source in _sources(prefs, "home")[:1]:
        add("consumption", KIND_CONSUMPTION, source.get("stat_rate"))
    for device in (prefs or {}).get("device_consumption") or []:
        if not isinstance(device, Mapping):
            continue
        stat_rate = device.get("stat_rate")
        identity = device.get("stat_consumption") or stat_rate
        if not isinstance(identity, str):
            continue
        add(
            device_channel_key(identity),
            KIND_DEVICE_POWER,
            stat_rate,
            name=device.get("name") or None,
        )

    known = {"grid", "solar", "battery", "home", "gas", "water"}
    for source in (prefs or {}).get("energy_sources") or []:
        source_type = source.get("type") if isinstance(source, Mapping) else None
        if source_type not in known and source_type not in _unknown_types_logged:
            _unknown_types_logged.add(str(source_type))
            _LOGGER.debug("Energy source type %s is not shared", source_type)
    return channels


def battery_capacity_kwh(prefs: Mapping[str, Any] | None) -> float | None:
    """Total usable battery capacity from the Energy settings, if any is set."""
    total = 0.0
    for source in _sources(prefs, "battery"):
        capacity = source.get("capacity")
        if isinstance(capacity, (int, float)) and capacity > 0:
            total += float(capacity)
    return round(total, 3) if total > 0 else None


def power_transforms(prefs: Mapping[str, Any] | None) -> list[PowerTransform]:
    """The power_configs of manual preferences that need a transform sensor.

    A single plain sensor (`stat_rate` inside `power_config`) needs none.
    """
    transforms: list[PowerTransform] = []
    for source_type in TRANSFORM_SOURCE_TYPES:
        for i, source in enumerate(_sources(prefs, source_type)):
            config = source.get("power_config")
            if not isinstance(config, Mapping) or "stat_rate" in config:
                continue
            transforms.append(PowerTransform(source_type, i, dict(config)))
    return transforms


def resolve_manual_preferences(
    prefs: Mapping[str, Any] | None,
    transform_entity_id: Callable[[PowerTransform], str | None],
) -> dict[str, Any]:
    """Fill grid and battery `stat_rate` from `power_config`, as Energy does.

    Mirrors `EnergyManager._process_grid_power` / `_process_battery_power`:
    a plain sensor is copied, a transform is replaced by the entity id of the
    transform sensor (looked up by `transform_entity_id`, None while it is not
    registered yet).
    """
    if not prefs:
        return {}
    transforms = {(t.source_type, t.index): t for t in power_transforms(prefs)}
    counters: dict[str, int] = {}
    sources: list[dict[str, Any]] = []
    for source in prefs.get("energy_sources") or []:
        if not isinstance(source, Mapping):
            continue
        out = dict(source)
        source_type = out.get("type")
        if source_type in TRANSFORM_SOURCE_TYPES:
            index = counters.get(source_type, 0)
            counters[source_type] = index + 1
            config = out.get("power_config")
            if isinstance(config, Mapping):
                if "stat_rate" in config:
                    out["stat_rate"] = config["stat_rate"]
                elif transform := transforms.get((source_type, index)):
                    out.pop("stat_rate", None)
                    if entity_id := transform_entity_id(transform):
                        out["stat_rate"] = entity_id
        sources.append(out)
    return {**prefs, "energy_sources": sources}


def validate_power_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a power_config with the Energy dashboard's own schema.

    Raises the schema library's Invalid error (voluptuous before 2026.10,
    probatio after); callers catch Exception for that reason.
    """
    return dict(POWER_CONFIG_SCHEMA(dict(config)))
