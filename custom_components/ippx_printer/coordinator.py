"""DataUpdateCoordinator for the IPPx Printer integration."""

from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry                            # type: ignore
from homeassistant.const import CONF_HOST, CONF_PORT                            # type: ignore
from homeassistant.core import HomeAssistant                                    # type: ignore
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator      # type: ignore
from datetime import timedelta
from typing import Any

from .const import CONF_MARKERS, CONF_SCHEMA, DOMAIN, STATUS_FIELDS, UPDATE_INTERVAL
from .helpers import fetch_printer_info

_LOGGER = logging.getLogger(__name__)


class IppxPrinterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the printer for status and marker levels."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""

        self.entry = entry
        self._host: str = entry.data[CONF_HOST]
        self._port: int = entry.data[CONF_PORT]
        self._schema: str = entry.data[CONF_SCHEMA]
        self._markers: list[dict[str, Any]] = entry.data.get(CONF_MARKERS, [])
        self._was_offline: bool = False

        super().__init__(
            hass,
            _LOGGER,
            name = f"{DOMAIN}_{entry.entry_id}",
            update_interval = timedelta(seconds = UPDATE_INTERVAL),
        )


    async def _async_update_data(self) -> dict[str, Any]:
        """Retrieves the live data from the printer."""

        result = await fetch_printer_info(self._host, self._port, schemas = [self._schema])
        if result is None:
            if not self._was_offline:
                _LOGGER.warning("Printer %s:%s not reachable", self._host, self._port)
                self._was_offline = True
            return{
                "printer-state": None,
                "printer-state-reasons": None,
                "markers": [],
                "offline": True
            }

        if self._was_offline:
            self._was_offline = False

        attrs = result["info"]
        data: dict[str, Any] = {field: attrs.get(field) for field in STATUS_FIELDS}

        levels = attrs.get("marker-levels") or []
        if not isinstance(levels, list):
            levels = [levels]

        marker_data: list[dict[str, Any]] = []
        for i, marker in enumerate(self._markers):
            level = None
            if i < len(levels):
                try:
                    level = int(levels[i])
                except (TypeError, ValueError):
                    level = None
            marker_data.append({**marker, "level": level})

        data["markers"] = marker_data
        data["offline"] = False
        return data