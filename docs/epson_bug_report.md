# Epson ET-4850 Series – IPP Bug Report

**Product:** Epson EcoTank ET-4850 Series

**Firmware Version:** 05.14.XA22Q5

**Connection:** IPP over IPPS (`ipps://<host>:631/ipp/print`)

**Tested with:** Home Assistant 2026.9.0 + `ippx` 0.1.1

This document describes two reproducible issues with the Epson ET-4850's IPP implementation that affect IPP clients such as Home Assistant, CUPS, and AirPrint.

---

## Bug 1: Marker attributes are not returned when explicitly requested

According to the IPP specification (RFC 8011), a printer **must** return the requested attributes when they are specified in `requested-attributes`. The ET-4850, however, does **not** return marker attributes when they are explicitly requested.

### Reproduction Bug 1

1. Send `Get-Printer-Attributes` with the following `requested-attributes`:
`printer-uuid, printer-name, printer-dns-sd-name, printer-make-and-model, printer-state, printer-state-reasons, media-default, media-supported, print-color-mode-default, print-color-mode-supported, print-content-optimize-default, print-content-optimize-supported, print-scaling-default, print-scaling-supported, media-type-supported, charset-configured, charset-supported, document-format-default, document-format-supported, marker-names, marker-types, marker-levels`

2. The response **does not** contain any `marker-*` attributes.

3. Send `Get-Printer-Attributes` **without** `requested-attributes` (full dump).

4. The marker attributes (`marker-names`, `marker-levels`, `marker-colors`, `marker-types`, `marker-low-levels`, `marker-high-levels`) are present in the response.

### Expected behavior Bug 1

The printer should return the requested marker attributes when they are explicitly requested — or at least return an error if it cannot deliver them.

### Actual behavior Bug 1

The attributes are silently omitted, even though they are present in the full dump.

### Impact Bug 1

IPP clients cannot reliably query marker levels. Ink/toner monitoring in Home Assistant, CUPS, and other IPP clients is broken unless the client requests **all** printer attributes and filters afterwards.

### Workaround Bug 1

Query **all** attributes without `requested-attributes` and filter on the client side.

---

## Bug 2: Progressive JPEGs are accepted but never printed

The ET-4850 lists `image/jpeg` in `document-format-supported`. However, when a **progressive JPEG** (SOF2) is submitted, the printer accepts the job (`job-state: 5`, `job-state-reasons: ['job-printing']`) but never prints it. The job silently disappears from the queue after a short time.

When a **baseline JPEG** (SOF0) is submitted with the same `document-format`, the printer prints it normally.

### Reproduction Bug 2

1. Send `Print-Job` with a **progressive JPEG** (`document_format="image/jpeg"`).
2. The printer responds with `successful-ok` and `job-state: 5` (PROCESSING).
3. `job-state-reasons: ['job-printing']`.
4. The job is never printed.
5. `Get-Jobs (which-jobs="not-completed")` returns `0` after a short while — the job was silently removed.

Repeat the same steps with a **baseline JPEG** → the printer prints it.

### Expected behavior Bug 2

One of the following:

- **Option A:** Reject the job with `client-error-document-format-not-supported` or `client-error-attributes-or-values-not-supported`.
- **Option B:** Accept the job but mark it as `ABORTED` with `job-state-reasons: ['document-format-error']` or `['unsupported-document-format']`.
- **Option C:** Print the progressive JPEG, since the printer claims to support `image/jpeg`.

### Actual behavior Bug 2

The job is reported as `PROCESSING` / `job-printing`, then silently removed. The client receives no error or completion feedback.

### Impact Bug 2

IPP clients cannot detect that a progressive JPEG was not printed. Users experience silent failures — especially when printing from sources that produce progressive JPEGs by default (e.g. PyMuPDF, some image editors, some scanners).

### Workaround Bug 2

Re-encode JPEGs as baseline (SOF0) before submitting. The `ippx_printer` Home Assistant integration uses Pillow to re-encode images as baseline JPEGs before submitting them.

---

## Additional Observations

### `printer-is-accepting-jobs` is `false` during printing

While a job is being processed (`printer-state: 4`, PROCESSING), the printer reports `printer-is-accepting-jobs: false`. This is technically correct — the printer cannot accept new jobs while busy — but it makes it harder for clients to distinguish "busy" from "error".

### `media-*-margin-supported` is `1setOf integer`, not `rangeOfInteger`

The printer returns, for example:
`media-top-margin-supported: [0, 300]`

This means only the values `0` and `300` are allowed, not a continuous range from 0 to 300. This is correct per the PWG specification, but should be documented for users.

### `job-creation-attributes-supported` does not include `document-format`

The attribute `document-format` is not listed in `job-creation-attributes-supported`, even though the printer accepts it in Print-Job requests. Clients must handle `document-format` separately from other job attributes.

---

## Environment

- **Printer:** Epson ET-4850 Series
- **Firmware:** 05.14.XA22Q5
- **Connection:** IPPS (TLS with self-signed certificate)
- **Client:** Home Assistant 2026.9.0 with `ippx` 0.1.1

---

## Notes

- All reproduction steps were performed on a local network with a single ET-4850 printer.
- The behavior is reproducible and was observed over multiple days.
- The same behavior may affect other Epson EcoTank models with similar firmware.

---
Date: September 21, 2026
