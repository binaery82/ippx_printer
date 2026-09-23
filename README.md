
# IPPx Printer for Home Assistant

![logo](custom_components/ippx_printer/brand/dark_icon.png)

A custom Home Assistant integration for monitoring and printing to IPP/IPPS printers. It uses **[`ippx`](https://pypi.org/project/ippx/)** for communication. It supports direct printing of files natively supported by the printer, as well as direct printing of PDF files or their automatic conversion to JPEG format.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

## 🛠️ Features

- **Automatic discovery** via Zeroconf (`_ipp._tcp` and `_ipps._tcp`)
- **Manual setup** via the IP address
- **Printer status sensor** (`idle`, `printing`, `stopped`)
- **Sensor for status details** (status reasons) in a readable format
- **Ink/toner level sensors** for each cartridge (with fallback naming)
- **Print services** for all file formats supported by the printer and for PDF files
- **Automatic conversion from PDF to JPEG** with baseline JPEG encoding
- **Service for querying printer capabilities** (supported job attributes)
- **Support for multiple printers** – one configuration entry per printer

## ☑️ Prerequisites

- Home Assistant 2026.9 or newer
- A network-enabled printer that supports IPP or IPPS
- The printer must be accessible from your Home Assistant instance

## 🗂️ Installation

### ![HACS Logo](https://avatars.githubusercontent.com/u/56713226?s=32) HACS (recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations** → **⋮** → **Custom repositories**.
3. Add `https://github.com/binaery82/ippx_printer` as an **Integration**.
4. Search for **IPPx Printer** and install it.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/ippx_printer` folder to the `config/custom_components/` directory of your Home Assistant installation.
2. Restart Home Assistant.

## ⛓️‍💥 Configuration

### Automatic detection

If your printer announces itself via Zeroconf, Home Assistant displays a notification. Click **Configure** to add it.

### Manual Setup

1. Go to **Settings** → **Devices & Services**.
2. Click **+ Add integration**.
3. Search for **IPPx Printer**.
4. Enter the printer's IP address, the port (default `631`), and a name.
5. Click **Submit**.

## 📑 Entities

For each configured printer, the integration creates:

| Entity | Description |
| - | - |
| **Status** | Current printer status (`idle`, `printing`, `stopped`) |
| **Status Reasons** | Reasons for the printer status (English only) |
| **\<Marker\> Level** | Ink/toner level per marker (one sensor per marker) |

All entities are grouped under a device named after your printer.

## 🔧 Services

### `ippx_printer.print_file`

Prints a single file (JPEG or another supported format).

| Field | Required | Description |
| - | - | - |
| `file_path` | 🗹 Yes | Path to the file (must be included in `allowlist_external_dirs`) |
| `document_format` | 🗹 Yes | MIME type (e.g., `image/jpeg`, `application/pdf`) |
| `attributes` | 🗷 No | IPP job attributes as key-value pairs |

📝 **Example:**

```yaml
service: ippx_printer.print_file
target:
  entity_id: sensor.epson_et_4850_series
data:
  file_path: "/config/www/photo.jpg"
  document_format: "image/jpeg"
  attributes:
    media: "iso_a4_210x297mm"
    copies: 1
    sides: "one-sided"
```

### `ippx_printer.print_pdf`

Prints a PDF file. If the printer supports PDF natively, the file is sent directly. Otherwise, each page will be converted to a baseline JPEG and printed as a separate job.

| field | Required | Description |
| - | - | - |
| `file_path` | 🗹 yes | Path to PDF file (must be included in `allowlist_external_dirs`) |
| `attributes` | 🗷 no | IPP job attributes as key-value pairs |

**⚠️ Note:** Duplex printing is **not possible** when the PDF is converted to JPEG, as each page is sent as a separate print job. The service automatically sets the `sides` parameter to `one-sided`.

📝 **Example:**

```yaml
service: ippx_printer.print_pdf
target:
  entity_id: sensor.epson_et_4850_series
data:
  file_path: "/config/www/document.pdf"
  attributes:
    media: "iso_a4_210x297mm"
    copies: 2
```

### `ippx_printer.get_capabilities`

Returns the printer functions relevant to print jobs. Similar to `weather.get_forecasts`, this service provides the data on demand rather than storing it permanently.

📝 **Example:**

```yaml
service: ippx_printer.get_capabilities
target:
  entity_id: sensor.epson_et_4850_series
response_variable: caps
```

📇 **Structure of the response:**

```yaml
document-format-default: application/octet-stream
document-format-supported: [...]
capabilities:
copies-default: 1
copies-supported: {min: 1, max: 99}
media-default: iso_a4_210x297mm
media-supported: [...]
media-col-default: {...}
media-col-supported: [...]
media-top-margin-supported: [0, 300]
media-type-supported: [...]
sides-default: one-sided
sides-supported: [...]
print-color-mode-default: auto
print-color-mode-supported: [...]
...
```

**Interpretation of the values:**

| Type | Meaning | Example |
| - | - | - |
| `{min, max}` | Continuous value range | `copies-supported: {min: 1, max: 99}` means that 1 to 99 copies can be printed |
| `[...]` (List) | Specific allowed values | `media-top-margin-supported: [0, 300]` means that only 0 or 300 are allowed |
| Single value | Only this value is allowed | `output-bin-supported: face-up` |

## 💾 File Access

Home Assistant restricts file access for security reasons. To print files, they must be located in a directory listed in the `allowlist_external_dirs` of your `configuration.yaml`:

```yaml
homeassistant:
allowlist_external_dirs:
- "/config/www"
- "/media"
```

Then use paths such as `/config/www/photo.jpg` or `/media/document.pdf`.

## 🪪 IPP Job Attributes

The `attributes` field accepts any IPP job attribute supported by the printer. Commonly used attributes:

| Attribute | Values | Example |
| - | - | - |
| `media` | Paper size | `iso_a4_210x297mm`, `na_letter_8.5x11in` |
| `media-type` | Paper type | `stationery`, `photographic`, `envelope` |
| `sides` | Duplex mode | `one-sided`, `two-sided-long-edge`, `two-sided-short-edge` |
| `print-color-mode` | Color mode | `color`, `monochrome`, `auto` |
| `print-quality` | Print quality | `3` (draft), `4` (normal), `5` (high) |
| `print-scaling` | Scaling | `auto`, `auto-fit`, `fill`, `fit`, `none` |
| `copies` | Number of copies | Integer (e.g., `1`, `2`, `5`) |
| `orientation-requested` | Orientation | `3` (portrait), `4` (landscape) |
| `output-bin` | Output bin | `face-up`, `face-down` |
| `media-col` | Complex media specification | Nested dictionary (see below) |

Use `ippx_printer.get_capabilities` to see which attributes your printer supports and which values ​​are valid.

### 📝 Example of `media-col`

The `media-col` attribute combines paper size and margins:

```yaml
attributes:
  media-col:
    media-size:
      x-dimension: 21000    # 210 mm in 1/100 mm
      y-dimension: 29700    # 297 mm in 1/100 mm
    media-top-margin: 300    # 3 mm in 1/100 mm
    media-left-margin: 300
    media-right-margin: 300
    media-bottom-margin: 300
    media-type: stationery
    media-source: main
```

**⚠️ Important:** Dimensions are specified in **1/100 mm**. Thus, `300` corresponds to `3 mm`. The printer may only support specific values ​​(e.g., `0` or `300` for the ET-4850). Check `media-top-margin-supported` in the response from `get_capabilities`.

## ❗Known Specifics

### Epson ET-4850 (and possibly other Epson models)

- **Marker fields are only transmitted when `requested-attributes` is omitted.** If the integration explicitly requests `marker-levels`, the printer does not return them. Therefore, the integration queries **all** attributes and then filters the results.
- **Progressive JPEGs are not printed.** Only baseline JPEGs (SOF0) work. The integration uses Pillow to convert PDF pages into baseline JPEGs.
- **`printer-is-accepting-jobs` is `false` during the printing process.** The integration waits until the printer is idle before sending the next page.
- **Bounds are of type `1setOf integer`, not `rangeOfInteger`.** Permissible values ​​are, for example, `[0, 300]` – not a continuous range of values.

Details can be found in the [bug report](docs/epson_bug_report.md).

## ⁉️ Troubleshooting

### "File not found" or "No access to file"

The file path is not included in `allowlist_external_dirs`. Add the parent directory to your `configuration.yaml` and restart Home Assistant.

### "Printer is not accepting jobs"

The printer is currently busy or reporting an error. Check the **Status Reasons** sensor and the printer display.

### "Format not supported"

The specified `document_format` is not included in the printer's `document-format-supported` list. Use `ippx_printer.get_capabilities` to view the supported formats.

### PDF prints only the first page

The printer does not support PDF natively, and the conversion failed. Check the Home Assistant log for details. Ensure that `pymupdf` and `pillow` are installed (these are dependencies of the integration).

### Printing is slow

For large or graphic-intensive files, the printer needs time. The integration waits between PDF pages for the printer to be ready again. This is normal.

## 💬 Development

### Structure

```none
custom_components/ippx_printer/
├── __init__.py          # Setup, unloading, service registration
├── config_flow.py       # Zeroconf and manual configuration flow
├── const.py             # Constants
├── coordinator.py       # DataUpdateCoordinator for status and markers
├── helpers.py           # URL generation, fetching, validation, PDF conversion
├── manifest.json        # Integration manifest
├── sensor.py            # Sensor entities
├── services.py          # Service handlers
├── services.yaml        # Service schemas
├── strings.json         # English translations
└── translations/
    └── de.json          # German translations
```

### Dependencies

- `ippx` – IPP client library
- `pymupdf` – PDF rendering
- `pillow` – Baseline JPEG encoding (already included in Home Assistant)

## License

See [LICENSE](LICENSE).

## Contribute

Issues and pull requests are welcome. If you find a bug or have a feature request, [please open an issue](https://github.com/binaery82/ippx_printer/issues).

## 🙏 Acknowledgments

- **[`ippx`](https://pypi.org/project/ippx/)** for the IPP client
- [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF rendering
- The Home Assistant community for documentation and examples

## Why ippx?

Before choosing `ippx`, I evaluated several alternatives:

- **CUPS:** Removed from Home Assistant in 2025.12. Not viable.
- **pyipp:** Great for reading printer status and attributes, but not designed for printing. No support for submitting jobs.
- **pycups:** Requires the CUPS C library and a running CUPS server. Installation inside Home Assistant OS is complicated (needs a C compiler and native dependencies), and not officially supported.

`ippx` is a pure-Python IPP client that supports both monitoring **and** printing. It works without native dependencies, is installable as a regular pip package, and covers the operations this integration needs:

- `get_printer_attributes()` – read status, markers, capabilities
- `print_job()` – submit print jobs with job attributes
- `get_jobs()` / `get_job_attributes()` – monitor job status
- `cancel_job()` – cancel pending jobs

Combined with `pymupdf` for PDF rendering and `pillow` for baseline JPEG encoding, this provides a complete printing solution without external services.

### Document format: why JPEG instead of PWG-Raster?

Many IPP printers support **PWG-Raster** (`image/pwg-raster`) as a document format. It's the format IPP Everywhere printers are required to support, and it would allow printing a multi-page PDF as a **single job** instead of one job per page.

However, there is currently **no pure-Python library** for generating PWG-Raster data. The available options require native dependencies:

- **CUPS filters** (`rastertopwg`, `pdftoraster`) – require a full CUPS installation with a C compiler and development headers.
- **`pycups`** – needs the CUPS C library and a running CUPS daemon.
- **`libcups`** – native C library, not available as a Python wheel.

Inside Home Assistant OS, installing native dependencies is either impossible or requires building a custom add-on. This makes PWG-Raster a non-viable path for a HACS-distributed integration **right now**.

**`image/jpeg` is the pragmatic choice:**

- Pure-Python encoding via **Pillow** (already a Home Assistant dependency).
- Supported by most network printers, including Epson, Canon, HP, and Brother.
- Works directly with `ippx` without native dependencies.
- PDF pages can be rendered to JPEG using **PyMuPDF** (also pure Python, no C compiler needed at runtime).

The main caveats:

- **JPEG is a single-page format.** A multi-page PDF must be sent as one print job per page. Duplex printing across pages is therefore not possible.
- **Some printers reject progressive JPEGs silently.** The integration re-encodes every image as baseline JPEG (SOF0) before submitting.

### Future outlook

If a pure-Python **PWG-Raster encoder** becomes available in the future, the integration could switch to PWG-Raster for multi-page jobs. This would:

- Allow printing a multi-page PDF as a **single job**.
- Enable **duplex printing** for multi-page documents.
- Reduce the number of IPP requests and improve printing speed.

We are tracking this possibility, but no such library exists today.
