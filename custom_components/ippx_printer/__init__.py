"""The IPPx Printer integration."""

from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry                            # type: ignore
from homeassistant.const import Platform                                        # type: ignore
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse     # type: ignore
from homeassistant.exceptions import ConfigEntryNotReady                        # type: ignore
from homeassistant.helpers import config_validation as cv                       # type: ignore
from homeassistant.helpers import device_registry as dr                         # type: ignore
from homeassistant.helpers.typing import ConfigType                             # type: ignore

from .coordinator import IppxPrinterCoordinator
from .services import (
    async_handle_print_file, 
    async_handle_print_pdf, 
    async_handle_get_capabilities,
)
from .const import (
    DOMAIN, 
    SERVICE_PRINT_FILE, 
    SERVICE_PRINT_PDF, 
    SERVICE_GET_CAPABILITIES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPPx Printer from a config entry."""

    coordinator = IppxPrinterCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_remove_config_entry_device(
        hass: HomeAssistant, 
        config_entry: ConfigEntry, 
        device_entry: dr.DeviceEntry,
    ) -> bool:
    """
    Allow manual removal of the device and its config entry.

    In our integration, one printer = one config entry = one device.
    Removing the device therefore also removes the config entry.
    """

    if not any(
        identifier[0] == DOMAIN and identifier[1] == config_entry.entry_id
        for identifier in device_entry.identifiers
    ):
        return False

    hass.async_create_task(
        hass.config_entries.async_remove(config_entry.entry_id)
    )
    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services."""

    async def handle_print_file(call: ServiceCall) -> None:
        await async_handle_print_file(hass, call)

    async def handle_print_pdf(call: ServiceCall) -> None:
        await async_handle_print_pdf(hass, call)

    async def handle_get_capabilities(call: ServiceCall) -> dict:
        return await async_handle_get_capabilities(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_FILE, handle_print_file)
    hass.services.async_register(DOMAIN, SERVICE_PRINT_PDF, handle_print_pdf)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CAPABILITIES,
        handle_get_capabilities,
        supports_response = SupportsResponse.ONLY,
    )
    return True


