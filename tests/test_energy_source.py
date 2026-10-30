"""Tests for reading channels from the Energy dashboard's model."""

from __future__ import annotations

import pytest

from custom_components.kilowattlas.energy_source import (
    Channel,
    PowerTransform,
    battery_capacity_kwh,
    device_channel_key,
    power_transforms,
    resolve_channels,
    resolve_manual_preferences,
    transform_unique_id,
    validate_power_config,
)


def test_full_home_maps_onto_kinds_and_keys() -> None:
    """Every power field becomes one channel, in Energy's own sign."""
    prefs = {
        "energy_sources": [
            {"type": "solar", "stat_rate": "sensor.solar"},
            {"type": "grid", "stat_rate": "sensor.grid"},
            {"type": "battery", "stat_rate": "sensor.bat", "stat_soc": "sensor.soc"},
            {
                "type": "home",
                "stat_energy_to": "sensor.home_e",
                "stat_rate": "sensor.home",
            },
            {
                "type": "gas",
                "stat_energy_from": "sensor.gas",
                "stat_rate": "sensor.gas_flow",
            },
        ],
        "device_consumption": [
            {
                "stat_consumption": "sensor.ev_energy",
                "stat_rate": "sensor.ev",
                "name": "Car",
            }
        ],
    }
    assert resolve_channels(prefs) == [
        Channel("", "gross_production", "sensor.solar"),
        Channel("grid", "grid_power", "sensor.grid"),
        Channel("battery", "battery_power", "sensor.bat"),
        Channel("battery_soc", "battery_soc", "sensor.soc", percent=True),
        Channel("consumption", "consumption", "sensor.home"),
        Channel("device_sensor.ev_energy", "device_power", "sensor.ev", name="Car"),
    ]


def test_second_sources_are_numbered_by_slot() -> None:
    """A second inverter is solar_2, even when the first has no power sensor."""
    prefs = {
        "energy_sources": [
            {"type": "solar", "stat_energy_from": "sensor.a_energy"},
            {"type": "solar", "stat_rate": "sensor.b"},
            {"type": "grid", "stat_rate": "sensor.g1"},
            {"type": "grid", "stat_rate": "sensor.g2"},
            {"type": "battery", "stat_rate": "sensor.b1"},
            {"type": "battery", "stat_rate": "sensor.b2", "stat_soc": "sensor.s2"},
        ]
    }
    assert [(c.key, c.entity_id) for c in resolve_channels(prefs)] == [
        ("solar_2", "sensor.b"),
        ("grid", "sensor.g1"),
        ("grid_2", "sensor.g2"),
        ("battery", "sensor.b1"),
        ("battery_2", "sensor.b2"),
        ("battery_soc_2", "sensor.s2"),
    ]


def test_skips_what_cannot_be_shared() -> None:
    """External statistics, missing fields, duplicates and unknown types."""
    prefs = {
        "energy_sources": [
            {"type": "solar", "stat_rate": "tibber:power"},  # external statistic
            {"type": "grid"},
            {"type": "community", "stat_rate": "sensor.future"},  # unknown type
            {"type": "home", "stat_energy_to": "sensor.h"},  # no power sensor
            "garbage",
        ],
        "device_consumption": [
            {"stat_consumption": "sensor.a_energy"},  # no power sensor
            {"stat_rate": "sensor.dup"},
            {"stat_rate": "sensor.dup"},
            {"name": "no identity"},
            "garbage",
        ],
    }
    assert resolve_channels(prefs) == [
        Channel("device_sensor.dup", "device_power", "sensor.dup")
    ]
    assert resolve_channels(None) == []
    assert resolve_channels({}) == []


def test_overrides_keep_pre_1_0_channels() -> None:
    """A sensor shared before 1.0.0 keeps its server channel and kind."""
    prefs = {"device_consumption": [{"stat_rate": "sensor.wallbox", "name": "EV"}]}
    channels = resolve_channels(
        prefs, {"sensor.wallbox": ["ev_charger", "ev_charger_power"]}
    )
    assert channels == [
        Channel("ev_charger", "ev_charger_power", "sensor.wallbox", "EV")
    ]


def test_device_channel_key_is_valid_and_bounded() -> None:
    """Server keys allow [A-Za-z0-9._-] and at most 64 characters."""
    assert device_channel_key("sensor.dishwasher") == "device_sensor.dishwasher"
    assert device_channel_key("tibber:energy") == "device_tibber_energy"
    assert len(device_channel_key("sensor." + "x" * 100)) == 64


def test_battery_capacity_sums_batteries() -> None:
    """The Energy dashboard's capacity, summed; unknown when none is set."""
    prefs = {
        "energy_sources": [
            {"type": "battery", "capacity": 10.0},
            {"type": "battery", "capacity": 5.5},
            {"type": "battery", "capacity": "bad"},
        ]
    }
    assert battery_capacity_kwh(prefs) == 15.5
    assert battery_capacity_kwh({"energy_sources": [{"type": "battery"}]}) is None
    assert battery_capacity_kwh(None) is None


def test_manual_preferences_resolve_power_config_like_energy() -> None:
    """A plain sensor is copied, a transform becomes its transform sensor."""
    prefs = {
        "energy_sources": [
            {"type": "grid", "power_config": {"stat_rate_inverted": "sensor.g"}},
            {"type": "battery", "power_config": {"stat_rate": "sensor.b"}},
            {
                "type": "battery",
                "power_config": {
                    "stat_rate_from": "sensor.out",
                    "stat_rate_to": "sensor.in",
                },
            },
            {"type": "solar", "stat_rate": "sensor.s"},
        ]
    }
    assert power_transforms(prefs) == [
        PowerTransform("grid", 0, {"stat_rate_inverted": "sensor.g"}),
        PowerTransform(
            "battery", 1, {"stat_rate_from": "sensor.out", "stat_rate_to": "sensor.in"}
        ),
    ]
    registered = {"grid": "sensor.kilowattlas_g_inverted"}
    resolved = resolve_manual_preferences(
        prefs, lambda t: registered.get(t.source_type)
    )
    rates = [s.get("stat_rate") for s in resolved["energy_sources"]]
    # The second battery's transform is not registered yet: no channel yet.
    assert rates == ["sensor.kilowattlas_g_inverted", "sensor.b", None, "sensor.s"]
    assert resolve_manual_preferences(None, lambda t: None) == {}
    assert transform_unique_id("e1", power_transforms(prefs)[0]) == "e1_grid_0_power"


@pytest.mark.parametrize(
    ("config", "valid"),
    [
        ({"stat_rate": "sensor.a"}, True),
        ({"stat_rate_inverted": "sensor.a"}, True),
        ({"stat_rate_from": "sensor.a", "stat_rate_to": "sensor.b"}, True),
        ({"stat_rate_from": "sensor.a"}, False),
        ({"stat_rate": "sensor.a", "stat_rate_inverted": "sensor.b"}, False),
        ({}, False),
    ],
)
def test_power_config_is_validated_by_energy(config: dict, valid: bool) -> None:
    """The Energy dashboard's own POWER_CONFIG_SCHEMA decides."""
    if valid:
        assert validate_power_config(config) == config
    else:
        with pytest.raises(Exception):  # noqa: B017 - voluptuous or probatio
            validate_power_config(config)
