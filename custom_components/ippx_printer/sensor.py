"""Sensor platform for the IPPx Printer integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity         # type: ignore
from homeassistant.components.sensor import SensorStateClass                        # type: ignore
from homeassistant.config_entries import ConfigEntry                                # type: ignore
from homeassistant.const import CONF_NAME, EntityCategory, PERCENTAGE               # type: ignore
from homeassistant.core import HomeAssistant                                        # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback               # type: ignore
from homeassistant.helpers.update_coordinator import CoordinatorEntity              # type: ignore
from typing import Any, Optional

from .coordinator import IppxPrinterCoordinator
from .helpers import format_option
from .const import (
    CONF_MARKERS, 
    CONF_PRINTER_MAKE_AND_MODEL, 
    DEFAULT_NAME, 
    DOMAIN, 
    STATE_MAP,
)


async def async_setup_entry(
        hass: HomeAssistant, 
        entry: ConfigEntry, 
        async_add_entities: AddEntitiesCallback
    ) -> None:
    """Create sensors from the config entry."""

    coordinator: IppxPrinterCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        IppxPrinterStatusSensor(coordinator, entry),
        IppxPrinterStatusReasonsSensor(coordinator, entry),
    ]
    for index, marker in enumerate(entry.data.get(CONF_MARKERS, [])):
        entities.append(IppxPrinterMarkerSensor(coordinator, entry, index, marker))

    async_add_entities(entities)


class _IppxPrinterBaseSensor(CoordinatorEntity[IppxPrinterCoordinator], SensorEntity):
    """Base class for all IPPx sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IppxPrinterCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get(CONF_NAME, DEFAULT_NAME),
            "manufacturer": "IPP Printer",
            "model": entry.data.get(CONF_PRINTER_MAKE_AND_MODEL, "Unknown"),        
        }


    @property
    def available(self) -> bool:
        """The sensor is available when the printer is reachable."""

        return not self.coordinator.data.get("offline", False)


class IppxPrinterStatusSensor(_IppxPrinterBaseSensor):
    """Displays the printer status in plain text."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "printing", "stopped", "unknown"]

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_name = None


    @property
    def native_value(self) -> Optional[str]:
        code = self.coordinator.data.get("printer-state")
        if code is None:
            return None
        try:
            return STATE_MAP.get(int(code), "unknown")
        except (TypeError, ValueError):
            return "unknown"


    @property
    def icon(self) -> str:
        value = self.native_value
        if value == "idle" or value == "printing":
            return "mdi:printer"
        if value == "stopped":
            return "mdi:alert"
        if value == "unknown":
            return "mdi:help"
        return "mdi:printer-off"


class IppxPrinterStatusReasonsSensor(_IppxPrinterBaseSensor):
    """Displays the printer-state-reasons as a list."""

    _attr_translation_key = "status_reasons"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC


    def __init__(self, coordinator , entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status_reasons"


    @property
    def native_value(self) -> str:
        reasons = self.coordinator.data.get("printer-state-reasons")
        if reasons is None:
            return "Unknown"
        if isinstance(reasons, str):
            reasons = [reasons]
        if not reasons:
            return "The printer is ready for use"

        cleaned = [r for r in reasons if str(r).lower() != "none"]
        if not cleaned:
            return "The printer is ready for use"

        formatted = [format_option(str(r)) for r in cleaned]
        return ", ".join(formatted)


    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        reasons = self.coordinator.data.get("printer-state-reasons")
        if isinstance(reasons, str):
            reasons = [reasons]
        return {"raw_reasons": reasons or []}


class IppxPrinterMarkerSensor(_IppxPrinterBaseSensor):
    """Displays the fill level of a marker (ink cartridge)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC


    def __init__(self, coordinator, entry, index: int, marker: dict[str, Any]):
        super().__init__(coordinator, entry)
        self._index = index
        self._marker_static = marker
        self._attr_unique_id = f"{entry.entry_id}_marker_{index}"
        self._attr_name = marker.get("name") or f"Color_{index + 1}"
        self._last_level: Optional[int] = None


    @property
    def native_value(self) -> Optional[int]:
        markers = self.coordinator.data.get("markers") or []
        if self._index < len(markers):
            level = markers[self._index].get("level")
            if level is not None:
                if level < 0:
                    level = 0
                self._last_level = level
                return level
        return self._last_level


    @property
    def icon(self) -> str:
        level = self.native_value
        if level is not None:
            low = self._marker_static.get("low")
            if low is not None and low > 0:
                if level <= low:
                    return "mdi:water-alert"
                high = self._marker_static.get("high")
                if high is not None and high > low:
                    center = int(round(((high - low) / 2) + low))
                    if level <= center:
                        return "mdi:water-opacity"
            return "mdi:water"
        return "mdi:water-off"


    @property
    def available(self) -> bool:
        """
        The sensor remains available even when the printer is offline. 

        The last known fill level is retained so that there are no gaps in the history.
        """

        return True
    

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "color": self._marker_static.get("color"),
            "type": self._marker_static.get("type"),
            "low": self._marker_static.get("low"),
            "high": self._marker_static.get("high"),
        }
