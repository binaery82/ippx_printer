"""Service handlers for the IPPX Printer integration."""

from __future__ import annotations

import logging
from pathlib import Path
from homeassistant.core import HomeAssistant, ServiceCall                           # type: ignore
from homeassistant.const import CONF_HOST, CONF_PORT                                # type: ignore
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError     # type: ignore
from homeassistant.helpers import entity_registry as er                             # type: ignore

from typing import Any, Optional
from .helpers import (
    build_printer_url, 
    convert_pdf_to_jpeg, 
    fetch_printer_info,
    wait_for_printer_ready,
)
from .const import (
    ATTR_ATTRIBUTES,
    ATTR_DOCUMENT_FORMAT, 
    ATTR_FILE_PATH,
    CONF_SCHEMA, 
    DEFAULT_JPEG_QUALITY,
    DEFAULT_PDF_DPI, 
    DOMAIN, 
    JOB_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


async def async_handle_print_file(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the print_file service call."""

    coordinator, entry = _get_coordinator_and_entry(hass, call)

    file_path = call.data[ATTR_FILE_PATH]
    document_format = call.data[ATTR_DOCUMENT_FORMAT]
    attributes = dict(call.data.get(ATTR_ATTRIBUTES, {}))

    printer_attrs = await _fetch_and_validate(entry, attributes, document_format)
    data = await _read_file(hass, file_path)
    url = build_printer_url(
        entry.data[CONF_SCHEMA],
        entry.data[CONF_HOST],
        entry.data[CONF_PORT]
    )

    _LOGGER.info(
        "[print_file %s] format=%s, attributes=%s.",
        file_path, document_format, attributes,
    )

    entry.async_create_background_task(
        hass,
        _print_job_background(
            coordinator = coordinator,
            url = url,
            data = data,
            document_format = document_format,
            job_attributes = attributes,
            description = f"print_file {file_path}"
        ),
        name = f"ippx_print_file_{entry.entry_id}",
    )


async def async_handle_print_pdf(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the print_pdf service call."""

    coordinator, entry = _get_coordinator_and_entry(hass, call)
    file_path = call.data[ATTR_FILE_PATH]
    attributes = dict(call.data.get(ATTR_ATTRIBUTES, {}))

    printer_attrs = await _fetch_and_validate(entry, attributes, None)
    pdf_bytes = await _read_file(hass, file_path)
    url = build_printer_url(
        entry.data[CONF_SCHEMA],
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
    )

    supported_formats = printer_attrs.get("document-format-supported", [])

    if "application/pdf" in supported_formats:
        _LOGGER.info("[print_pdf %s] format=application/pdf (native)", file_path,)
        entry.async_create_background_task(
            hass,
            _print_job_background(
                coordinator = coordinator,
                url = url,
                data = pdf_bytes,
                document_format ="application/pdf",
                job_attributes = attributes,
                description = f"print_pdf {file_path}",
            ),
            name = f"ippx_print_pdf_{entry.entry_id}",
        )
        return

    if "image/jpeg" not in supported_formats:
        raise ServiceValidationError("Neither PDF nor JPEG is supported by this printer.")
        
    try:
        pages = await hass.async_add_executor_job(
            convert_pdf_to_jpeg,
            pdf_bytes,
            DEFAULT_PDF_DPI,
            DEFAULT_JPEG_QUALITY,
        )
    except Exception as err:
        raise HomeAssistantError(f"PDF conversion failed: {err}.") from err

    if not pages:
        raise ServiceValidationError("PDF contains no pages.")

    if "sides" in attributes and attributes["sides"] != "one-sided":
        _LOGGER.warning(
            "[print_pdf %s] Duplex printing is not possible with JPEG fallback. "
            "Set pages to 'one-sided'.",
            file_path,
        )
    attributes["sides"] = "one-sided"

    _LOGGER.info(
        "[print_pdf %s] %s pages converted, attributes=%s.",
        file_path, len(pages), attributes,
    )

    entry.async_create_background_task(
        hass,
        _print_pdf_pages_background(
            coordinator = coordinator,
            url = url,
            pages = pages,
            job_attributes = attributes,
            description = f"print_pdf {file_path}",
        ),
        name = f"ippx_print_pdf_{entry.entry_id}",
    )


async def async_handle_get_capabilities(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Provides the job-relevant capabilities of the printer."""

    _coordinator, entry = _get_coordinator_and_entry(hass, call)
    result = await fetch_printer_info(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        schemas = [entry.data[CONF_SCHEMA]],
    )
    if result is None:
        raise ServiceValidationError("Printer is not reachable.")

    attrs = result["info"]
    capabilities: dict[str, Any] = {}
    job_attr = attrs.get("job-creation-attributes-supported", [])
    if not job_attr:
        _LOGGER.warning(
            "Printer does not return 'job-creation-attributes-supported'. Return is empty."
        )

    for key in ("document-format-default", "document-format-supported"):
        if key in attrs:
            capabilities[key] = _to_serializable(attrs[key])

    for attr in job_attr:
        for suffix in ("-default", "-supported"):
            key = f"{attr}{suffix}"
            if key in attrs:
                capabilities[key] = _to_serializable(attrs[key])

    media_col_supported = attrs.get("media-col-supported", [])
    for member in media_col_supported:
        key = f"{member}-supported"
        if key in attrs:
            capabilities[key] = _to_serializable(attrs[key])

    return {"capabilities": capabilities}


def _to_serializable(value: Any) -> Any:
    """Converts IPP objects into JSON-serializable types."""

    if isinstance(value, tuple) and len(value) == 2:
        return {"min": _to_serializable(value[0]), "max": _to_serializable(value[1])}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_to_serializable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    if isinstance(value, bytes):
        return value.decode("utf-8", errors = "replace")
    return str(value)


def _get_coordinator_and_entry(hass: HomeAssistant, call: ServiceCall):
    """Determines the Coordinator and Config Entry from the Target entity."""

    entity_ids = call.data.get("entity_id")
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    if not entity_ids:
        raise ServiceValidationError("No printer selected.")

    ent_reg = er.async_get(hass)
    entity_entry = ent_reg.async_get(entity_ids[0])
    if entity_entry is None or entity_entry.config_entry_id is None:
        raise ServiceValidationError("Printer entity not found.")

    coordinator = hass.data.get(DOMAIN, {}).get(entity_entry.config_entry_id)
    if coordinator is None:
        raise ServiceValidationError("No coordinator for this printer.")

    return coordinator, coordinator.entry
 

async def _read_file(hass: HomeAssistant, file_path: str) -> bytes:
    """Reads a file and returns its bytes."""

    path = Path(file_path)
    if not path.is_file():
        raise ServiceValidationError(f"File not found: {file_path}.")
    try:
        return await hass.async_add_executor_job(path.read_bytes)
    except PermissionError as err:
        raise ServiceValidationError(
            f"No access to {file_path}. Add the path to allowlist_external_dirs."
        ) from err


async def _fetch_and_validate(
        entry,
        attributes: dict,
        document_format: Optional[str],
    ) -> dict:
    """Fetches fresh printer attributes and validates the job attributes."""

    result = await fetch_printer_info(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        schemas = [entry.data[CONF_SCHEMA]],
    )
    if result is None:
        raise ServiceValidationError(
            f"Printer {entry.data[CONF_HOST]}:{entry.data[CONF_PORT]} is not reachable."
        )

    printer_attrs = result["info"]
    if not printer_attrs.get("printer-is-accepting-jobs", True):
        reasons = printer_attrs.get("printer-state-reasons", "unknown")
        raise ServiceValidationError(f"Printer is not accepting jobs. Status: {reasons}")

    if document_format:
        supported_formats = printer_attrs.get("document-format-supported", [])
        if supported_formats and document_format not in supported_formats:
            raise ServiceValidationError(
                f"Format '{document_format}' is not supported. Possible: {', '.join(supported_formats)}."
            )

    job_attrs_supported = printer_attrs.get("job-creation-attributes-supported", [])
    for ipp_key in attributes:
        if job_attrs_supported and ipp_key not in job_attrs_supported:
            _LOGGER.warning(
                "Attribute '%s' is not in job-creation-attributes-supported. "
                "The printer may ignore it.",
                ipp_key,
            )    

    for ipp_key, value in attributes.items():
        if ipp_key == "media-col":
            _validate_media_col(printer_attrs, value)
            continue
        supported = printer_attrs.get(f"{ipp_key}-supported")
        if supported is None:
            continue
        _validate_value(ipp_key, value, supported)

    return printer_attrs


def _validate_value(ipp_key: str, value: Any, supported: Any) -> None:
    """Checks a single value against a -supported-list."""

    if isinstance(supported, tuple) and len(supported) == 2:
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise ServiceValidationError(f"Value '{value}' for '{ipp_key}' must be a number.")
        if not (supported[0] <= v <= supported[1]):
            raise ServiceValidationError(
                f"Value '{value}' for '{ipp_key}' is outside the range {supported[0]}–{supported[1]}."
            )
        return

    if isinstance(supported, list):
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v not in supported:
                raise ServiceValidationError(
                    f"Value '{v}' for '{ipp_key}' is not supported. "
                    f"Possible: {', '.join(str(s) for s in supported)}."
                )
        return

    if value != supported:
        raise ServiceValidationError(
            f"Value '{value}' for '{ipp_key}' is not supported. Allowed: {supported}."
        )
    

def _validate_media_col(printer_attrs: dict, media_col: Any) -> None:
    """Checks media-col against media-col-supported and the individual fields."""

    if not isinstance(media_col, dict):
        raise ServiceValidationError("media-col must be a dict.")

    supported_members = printer_attrs.get("media-col-supported", [])
    if not supported_members:
        return

    for member_key, member_value in media_col.items():
        if member_key not in supported_members:
            raise ServiceValidationError(
                f"media-col-Member '{member_key}' is not supported. Possible: {', '.join(supported_members)}."
            )

        member_supported = printer_attrs.get(f"{member_key}-supported")
        if member_supported is not None:
            _validate_value(member_key, member_value, member_supported)


async def _print_job_background(
        coordinator,
        url: str,
        data: bytes,
        document_format: str,
        job_attributes: dict,
        description: str,
) -> None:
    """Submits a single job and waits in the background for completion."""

    from ippx import AsyncIppClient, TlsConfig
    client = AsyncIppClient(url, tls = TlsConfig(verify = False))
    try:
        async with client:
            job = await client.print_job(
                data,
                document_format = document_format,
                job_attributes = job_attributes,
            )
            _LOGGER.info(
                "[%s] Job %s sent (format=%s, state=%s, reasons=%s).",
                description,
                job.job_id,
                document_format,
                job.state,
                job.state_reasons,
            )
            _log_problem_reasons(job, description)

            try:
                final = await client.wait_for_job(job.job_id, timeout = JOB_TIMEOUT)
                _log_final_state(final, description, job.job_id)
            except Exception as err:
                _LOGGER.warning(
                    "[%s] Waiting for job %s failed: %s.",
                    description, job.job_id, err,
                )
    except Exception as err:
        _LOGGER.error("[%s] Printing failed: %s.", description, err,)
    finally:
        await coordinator.async_request_refresh()


async def _print_pdf_pages_background(
        coordinator,
        url: str,
        pages: list[bytes],
        job_attributes: dict,
        description: str,
    ) -> None:
    """Sends all PDF pages and waits for each one."""

    from ippx import AsyncIppClient, TlsConfig
    total = len(pages)
    client = AsyncIppClient(url, tls = TlsConfig(verify = False))
    try:
        async with client:
            for index, page_data in enumerate(pages, start = 1):
                try:
                    await wait_for_printer_ready(url, timeout = JOB_TIMEOUT)
                except TimeoutError as err:
                    _LOGGER.error(
                        "[%s] Printer not ready for page %d/%d: %s",
                        description, index, total, err,
                    )
                    return
                try:
                    job = await client.print_job(
                        page_data,
                        document_format = "image/jpeg",
                        job_attributes = job_attributes
                    )
                except Exception as err:
                    _LOGGER.error(
                        "[%s] Page %d/%d failed: %s.",
                        description, index, total, err,
                    )
                    return

                _LOGGER.info(
                    "[%s] Page %d/%d sent as job %s (state=%s, reasons=%s).",
                    description,index, total, job.job_id, job.state, job.state_reasons,
                )
                _log_problem_reasons(job, description)

            _LOGGER.info("[%s] All %d pages sent.", description, total,)
    except Exception as err:
        _LOGGER.error("[%s] PDF printing failed: %s.", description, err,)
    finally:
        await coordinator.async_request_refresh()


def _log_problem_reasons(job, description: str) -> None:
    """Logs problematic state_reasons."""

    reasons = job.state_reasons or []
    problem_reasons = [
        r for r in reasons 
        if r not in ("job-printing", "job-completed-successfully", "none")
    ]
    if problem_reasons:
        _LOGGER.warning(
            "[%s] Job %s reports problems: %s.",
            description, job.job_id, ", ".join(problem_reasons),
        )


def _log_final_state(job, description: str, job_id: int) -> None:
    """Logs the final state of a job."""

    state = job.state
    reasons = job.state_reasons
    if state == 9:
        _LOGGER.info(
            "[%s] Job %s successfully completed (%s).",
            description, job_id, reasons, 
        )
    else:
        _LOGGER.warning(
            "[%s] Job %s ended with state=%s, reasons=%s.",
            description, job_id, state, reasons,
        )
