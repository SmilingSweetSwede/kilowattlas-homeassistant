"""Sensors showing what is being shared with Kilowattlas, and how it is going."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAP_BASE_URL, STATUSES
from .coordinator import KilowattlasConfigEntry, KilowattlasCoordinator, KilowattlasData

# Push-based: entities update when the coordinator publishes, never by polling.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KilowattlasSensorDescription(SensorEntityDescription):
    """Describes a Kilowattlas sensor."""

    value_fn: Callable[[KilowattlasData], float | int | str | datetime | None]
    requires_source: bool = False


SENSORS: tuple[KilowattlasSensorDescription, ...] = (
    KilowattlasSensorDescription(
        key="shared_production",
        translation_key="shared_production",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: d.current_kw,
        requires_source=True,
    ),
    KilowattlasSensorDescription(
        key="sharing_status",
        translation_key="sharing_status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUSES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.status,
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
    """Set up the sensors for a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        KilowattlasSensor(coordinator, description) for description in SENSORS
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
            model="Solar sharing",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=map_url(coordinator.hass),
        )

    @property
    def available(self) -> bool:
        """Production is unavailable while the source sensor is."""
        if not super().available:
            return False
        if self.entity_description.requires_source:
            return self.coordinator.data.source_available
        return True

    @property
    def native_value(self) -> float | int | str | datetime | None:
        """Return the value from the latest snapshot."""
        return self.entity_description.value_fn(self.coordinator.data)
