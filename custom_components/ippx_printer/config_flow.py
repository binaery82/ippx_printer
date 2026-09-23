"""Config flow for IPPx Printer integration."""

from __future__ import annotations

import logging
import voluptuous as vol
from homeassistant import config_entries                                            # type: ignore
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT                     # type: ignore
from homeassistant.data_entry_flow import FlowResult                                # type: ignore
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo         # type: ignore
from typing import Any, Optional

from .helpers import extract_markers, fetch_printer_info, is_valid_ip
from .const import (
    CONF_MARKERS, 
    CONF_SCHEMA, 
    CONF_PRINTER_MAKE_AND_MODEL, 
    DEFAULT_NAME, 
    DEFAULT_PORT, 
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class IppxPrinterConfigFlow(config_entries.ConfigFlow, domain = DOMAIN):
    """ Config flow for IPPx Printer. """

    VERSION = 1

    def __init__(self):
        """Initialize flow state."""

        self._host: Optional[str] = None
        self._port: int = DEFAULT_PORT
        self._name: str = DEFAULT_NAME
        self._uuid: Optional[str] = None
        self._schema: Optional[str] = None
        self._markers: list[dict[str, Any]] = []
        self._make_and_model: str = "Unknown"

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> FlowResult:
        """Handle Zeroconf discovery."""

        self._host = discovery_info.host
        self._port = discovery_info.port or DEFAULT_PORT

        result = await fetch_printer_info(self._host, self._port)
        if result is None:
            _LOGGER.debug("No connection to: %s:%s.", self._host, self._port,)
            return self.async_abort(reason = "cannot_connect")

        self._uuid = result.get("uuid")
        if not self._uuid:
            _LOGGER.debug("No UUID found on %s:%s.", self._host, self._port,)
            return self.async_abort(reason = "uuid_not_found")

        await self.async_set_unique_id(self._uuid)
        self._abort_if_unique_id_configured(
            updates = {CONF_HOST: self._host, CONF_PORT: self._port}
        )

        self._name = result.get("name", DEFAULT_NAME)
        self._schema = result.get("schema")
        self._markers = extract_markers(result["info"])
        self._make_and_model = result["info"].get("printer-make-and-model", "Unknown")

        return await self.async_step_confirm()


    async def async_step_confirm(self, user_input: Optional[dict[str, Any]] = None) -> FlowResult:
        """The user confirms the discovery and can change the name."""

        if user_input is not None:
            self._name = user_input.get(CONF_NAME, DEFAULT_NAME)
            return self._create_entry()

        return self.async_show_form(
            step_id = "confirm",
            data_schema = vol.Schema({vol.Required(CONF_NAME, default = self._name):str}),
            description_placeholders = {"host": self._host or "", "model": self._name},
        )


    async def async_step_user(self, user_input: Optional[dict[str, Any]] = None) -> FlowResult:
        """Manual setup via IP address."""

        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST, "").strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            name = user_input.get(CONF_NAME, DEFAULT_NAME)

            if not host:
                errors[CONF_HOST] = "ip_required"
            elif not is_valid_ip(host):
                errors[CONF_HOST] = "invalid_ip"
            else:
                result = await fetch_printer_info(host, port)
                if result is None:
                    errors[CONF_HOST] = "cannot_connect"
                elif not result.get("uuid"):
                    _LOGGER.debug("No UUID found at %s:%s.", host, port,)
                    errors[CONF_HOST] = "uuid_not_found"
                else:
                    await self.async_set_unique_id(result["uuid"])
                    self._abort_if_unique_id_configured(
                        updates = {CONF_HOST: host, CONF_PORT: port}
                    )
                    self._name = name
                    self._host = host
                    self._port = port
                    self._schema = result["schema"]
                    self._markers = extract_markers(result["info"])
                    self._make_and_model = result["info"].get("printer-make-and-model", "Unknown")
                    return self._create_entry()

        return self.async_show_form(
            step_id = "user",
            data_schema = vol.Schema(
                {
                    vol.Required(CONF_NAME, default = self._name): str,
                    vol.Required(CONF_HOST, default = self._host or ""): str,
                    vol.Required(CONF_PORT, default = self._port): int
                }
            ),
            errors = errors
        )


    def _create_entry(self) -> FlowResult:
        """Create the config entry from either flow path."""

        return self.async_create_entry(
            title = self._name,
            data = {
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_NAME: self._name,
                CONF_SCHEMA: self._schema,
                CONF_MARKERS: self._markers,
                CONF_PRINTER_MAKE_AND_MODEL: self._make_and_model
            },
        )
