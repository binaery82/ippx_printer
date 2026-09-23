"""Constants for the IPPx Printer integration."""

DOMAIN = "ippx_printer"
UPDATE_INTERVAL = 60

# --- Connection ---
DEFAULT_NAME = "IPPx Printer"
DEFAULT_PORT = 631
DEFAULT_PATH = "/ipp/print"
DEFAULT_SCHEMAS = ["ipps", "ipp"]

# --- Config-Entry-Keys --- 
CONF_SCHEMA = "schema"
CONF_MARKERS = "markers"
CONF_PRINTER_MAKE_AND_MODEL = "printer-make-and-model"

# --- Service ---
SERVICE_PRINT_FILE = "print_file"
SERVICE_PRINT_PDF = "print_pdf"
SERVICE_GET_CAPABILITIES = "get_capabilities"
ATTR_FILE_PATH = "file_path"
ATTR_ATTRIBUTES = "attributes"
ATTR_DOCUMENT_FORMAT = "document_format"
DEFAULT_PDF_DPI = 300
DEFAULT_JPEG_QUALITY = 90
JOB_TIMEOUT = 300

# --- Marker-Fields ---
MARKER_STATIC_FIELDS = (
    "marker-names",
    "marker-colors",
    "marker-types",
    "marker-low-levels",
    "marker-high-levels",
)

MARKER_DYNAMIC_FIELDS = (
    "marker-levels",
)

# --- Status-Fields ---
STATUS_FIELDS = (
    "printer-state",
    "printer-state-reasons",
)

# --- Mapping printer-state ---
STATE_MAP = {
    3: "idle",
    4: "printing",
    5: "stopped",
}
