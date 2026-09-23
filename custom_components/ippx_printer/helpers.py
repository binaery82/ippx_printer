"""Helper functions for IPPx Printer integration."""

from __future__ import annotations

import logging
import asyncio
import ipaddress
import os
import tempfile
from typing import Any, Optional, List, Dict
from ippx import AsyncIppClient, TlsConfig

from .const import DEFAULT_NAME, DEFAULT_PATH, DEFAULT_SCHEMAS

_LOGGER = logging.getLogger(__name__)


def build_printer_url(schema: str, host: str, port: int) -> str:
    """Constructs the IPP URL from the schema, host, and port."""

    return f"{schema}://{host}:{port}{DEFAULT_PATH}"


async def fetch_printer_info(
        host: str, 
        port: int, 
        schemas: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
    """
    Test the connection to the printer and retrieve ALL attributes.

    Deliberately done WITHOUT `requested_attributes`, 
    because some printers (e.g., Epson ET-4850) do not return marker fields 
    if they are explicitly requested. 
    Filtering takes place in `extract_markers()`.

    Attempts the schemes in the specified order (default: ipps, ipp). 
    Returns `None` if none work. 

    Returns:
        {
            "uuid":   str | None,
            "name":   str,
            "info":   dict,   # full attribute dump
            "schema": str,    # the scheme that worked
        }    
    """

    for schema in (schemas or DEFAULT_SCHEMAS):
        url = build_printer_url(schema, host, port)
        client = AsyncIppClient(url, tls = TlsConfig(verify = False))
        try:    
            async with client:
                printer = await client.get_printer_attributes()
        except Exception as err:
            _LOGGER.debug(
                "Connection test via %s to %s:%s failed: %s",
                schema, host, port, err,
            )
            continue

        attrs = printer.attributes
        return {
            "uuid": attrs.get("printer-uuid"), 
            "name": _pick_name(attrs), 
            "info": attrs, 
            "schema": schema,
        }
    return None


def _pick_name(attrs: dict[str, Any]) -> str:
    """Select the best available name from the attributes."""

    for key in ("printer-make-and-model", "printer-dns-sd-name", "printer-name"):
        value = attrs.get(key)
        if value:
            return str(value)
    return DEFAULT_NAME


def extract_markers(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Builds the static marker structure from the IPP attributes. 

    Called once during setup and stored in the config entry. 
    The level values are provided later by the coordinator. 

    Fallback for names:
        1. marker-names[i]
        2. f"{marker-types[i]}_{i+1}"
        3. f"Color_{i+1}"    
    """

    names = _to_list(attrs.get("marker-names"))
    colors = _to_list(attrs.get("marker-colors"))
    types = _to_list(attrs.get("marker-types"))
    lows = _to_list(attrs.get("marker-low-levels"))
    highs = _to_list(attrs.get("marker-high-levels"))

    count = max(len(names), len(colors), len(types), len(lows), len(highs))
    if count == 0:
        return []

    markers: list[dict[str, Any]] = []
    for i in range(count):
        markers.append({
            "name": _pick_marker_name(i, names, types),
            "color": colors[i] if i < len(colors) else None,
            "type": types[i] if i < len(types) else None,
            "low": _to_int(lows[i]) if i < len(lows) else None,
            "high": _to_int(highs[i]) if i < len(highs) else None
        })
    return markers


def _pick_marker_name(index: int, names: list[Any], types: list[Any]) -> str:
    """Select the name for a marker based on fallback logic."""

    if index < len(names) and names[index]:
        return str(names[index])
    if index < len(types) and types[index]:
        return f"{types[index]}_{index + 1}"
    return f"Color_{index + 1}"


def _to_list(value: Any) -> list[Any]:
    """Converts a single value into a list; leaves lists unchanged."""

    if value is None:
        return []
    if isinstance(value, list):
        return [_to_primitive(v) for v in value]
    return [_to_primitive(value)]


def _to_primitive(value: Any) -> Any:
    """Converts values ​​into JSON-serializable types."""

    if value is None:
        return None
    if isinstance(value, bytes):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _to_int(value: Any) -> Optional[int]:
    """Converts a value to int; returns None on error."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_valid_ip(ip: str) -> bool:
    """Checks whether the string is a valid IP address (IPv4 or IPv6)."""

    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        _LOGGER.warning("Invalid IP address: ip=%s", ip,)
        return False


def format_option(value: str) -> str:
    """
    Formats an IPP string for display. 

    iso_a4_210x297mm → Iso A4 210x297mm
    """

    cleaned = value.replace("-", " ").replace("_", " ")
    return " ".join(
        word[0].upper() + word[1:] if word else word 
        for word in cleaned.split()
    )


def convert_pdf_to_jpeg(pdf_bytes: bytes, dpi: int = 300, quality: int = 90) -> list[bytes]:
    """
    Converts ALL pages of a PDF into baseline JPEGs. 

    By default, PyMuPDF generates progressive JPEGs, which the Epson ET-4850 cannot print.
    This necessitates using Pillow, which produces true baseline JPEGs (SOF0). 

    Returns: A list containing one baseline JPEG per page.
    """

    import pymupdf
    from io import BytesIO
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix = ".pdf", delete = False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        doc = pymupdf.open(tmp_path)
        try:
            pages: list[bytes] = []
            for page in doc:
                pix = page.get_pixmap(dpi = dpi)
                png_bytes = pix.tobytes("png")

                img = Image.open(BytesIO(png_bytes))
                if img.mode != "RGB":
                    img = img.convert("RGB")

                out = BytesIO()
                img.save(out, format = "JPEG", quality = quality, progressive = False)
                pages.append(out.getvalue())
            return pages
        finally:
            doc.close()
    finally:
        os.unlink(tmp_path)


async def wait_for_printer_ready(
        url: str, 
        timeout: float = 300, 
        interval: float = 3
    ) -> None:
    """
    Waits until the printer is ready for the next job. 

    Checks:
        - printer-is-accepting-jobs: True
        - printer-state: 3 (idle) or 4 (processing, if the last job is still running)

    Raises TimeoutError if the printer does not become ready in time.
    """

    client = AsyncIppClient(url, tls = TlsConfig(verify = False))
    elapsed = 0

    try:
        async with client:
            while elapsed < timeout:
                try:
                    printer = await client.get_printer_attributes(
                        requested_attributes = [
                            "printer-state",
                            "printer-is-accepting-jobs",
                            "printer-state-reasons"
                        ]
                    )
                except Exception as err:
                    _LOGGER.debug("Printer status query failed: %s", err)
                    await asyncio.sleep(interval)
                    elapsed += interval
                    continue

                accepting = printer.attributes.get("printer-is-accepting-jobs", False)
                state = printer.attributes.get("printer-state")
                reasons = printer.attributes.get("printer-state-reasons")

                if accepting or state == 3:
                    return

                await asyncio.sleep(interval)
                elapsed += interval
    finally:
        pass

    raise TimeoutError(f"The printer did not become ready within {timeout} seconds.")