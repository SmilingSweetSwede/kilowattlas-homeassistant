"""Sensors showing how sharing with Kilowattlas is going.

For homes that entered their sensors in this integration instead of the Energy
settings, this platform also sets up the Energy dashboard's own power
transform sensor (`homeassistant.components.energy.sensor.EnergyPowerSensor`)
for every inverted or two-sensor `power_config`, exactly as the Energy
dashboard does for its own settings.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.energy.helpers import generate_power_sensor_entity_id
from homeassistant.components.energy.sensor import EnergyPowerSensor
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_PREFERENCES,
    CONF_SOURCE,
    DOMAIN,
    MAP_BASE_URL,
    SOURCE_MANUAL,
    STATUSES,
)
from .coordinator import KilowattlasConfigEntry, KilowattlasCoordinator, KilowattlasData
from .energy_source import power_transforms, transform_unique_id

# Push-based: entities update when the coordinator publishes, never by polling.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KilowattlasSensorDescription(SensorEntityDescription):
    """Describes a Kilowattlas sensor."""

    value_fn: Callable[[KilowattlasData], float | int | str | datetime | None]


SENSORS: tuple[KilowattlasSensorDescription, ...] = (
    KilowattlasSensorDescription(
        key="sharing_status",
        translation_key="sharing_status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUSES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.status,
    ),
    KilowattlasSensorDescription(
        key="shared_channels",
        translation_key="shared_channels",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.shared_channels,
    ),
    KilowattlasSensorDescription(
        key="last_sent",
        translation_key="last_sent",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.last_push,
    ),
    KilowattlasSensorDescription(
        key="queued_readings",
        translation_key="queued_readings",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.pending_count,
    ),
    KilowattlasSensorDescription(
        key="last_batch_rejected",
        translation_key="last_batch_rejected",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.last_rejected,
    ),
    KilowattlasSensorDescription(
        key="measured_sample_interval",
        translation_key="measured_sample_interval",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.measured_sample_interval_seconds,
    ),
    KilowattlasSensorDescription(
        key="unusable_readings",
        translation_key="unusable_readings",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.unusable,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KilowattlasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the status sensors, and power transforms for manual preferences."""
    coordinator = entry.runtime_data
    async_add_entities(
        KilowattlasSensor(coordinator, description) for description in SENSORS
    )

    transforms = (
        power_transforms(entry.options.get(CONF_PREFERENCES))
        if entry.options.get(CONF_SOURCE) == SOURCE_MANUAL
        else []
    )
    wanted = {transform_unique_id(entry.entry_id, t) for t in transforms}
    # A transform that is no longer configured (changed in the options, or
    # the home switched to its Energy settings) leaves no entity behind.
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id.endswith("_power") and reg_entry.unique_id not in wanted:
            registry.async_remove(reg_entry.entity_id)
    async_add_entities(
        EnergyPowerSensor(
            t.source_type,
            t.config,  # type: ignore[arg-type]
            transform_unique_id(entry.entry_id, t),
            # The Energy dashboard's own naming, prefixed so the entity never
            # collides with the one it creates if the same power_config is
            # later entered in the Energy settings.
            generate_power_sensor_entity_id(t.source_type, t.config).replace(  # type: ignore[arg-type]
                "sensor.", f"sensor.{DOMAIN}_", 1
            ),
        )
        for t in transforms
    )


def map_url(hass: HomeAssistant) -> str:
    """Public map URL centred on this home's position."""
    lat, lng = hass.config.latitude, hass.config.longitude
    if lat is None or lng is None:
        return MAP_BASE_URL
    return f"{MAP_BASE_URL}/?lat={lat}&lng={lng}&zoom=13"


class KilowattlasSensor(CoordinatorEntity[KilowattlasCoordinator], SensorEntity):
    """One value from the coordinator's snapshot."""

    entity_description: KilowattlasSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KilowattlasCoordinator,
        description: KilowattlasSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Kilowattlas",
            manufacturer="Kilowattlas",
            model="Energy sharing",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=map_url(coordinator.hass),
        )

    @property
    def native_value(self) -> float | int | str | datetime | None:
        """Return the value from the latest snapshot."""
        return self.entity_description.value_fn(self.coordinator.data)
