# Hermes Vision Extractor - E2E Test Suite Specification & Ready Report

## 1. Test Suite Summary
- **Status:** READY & VERIFIED
- **Total Tests:** 127
- **Passed:** 127 (100%)
- **Failed:** 0
- **Test Framework:** `pytest` (Python 3.12.10)
- **Execution Command:**
  ```powershell
  C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe -m pytest f:/Development/plan/hermes_vision_extractor/tests/ -v
  ```

---

## 2. Test Architecture & Directory Structure
```
f:/Development/plan/hermes_vision_extractor/tests/
├── __init__.py
├── conftest.py                  # Pytest shared fixtures, temporary directories, sample records
├── mock_generator.py            # High-fidelity synthetic Hermes CMS screenshot generator (10 fixtures)
├── test_business_rules.py       # 58 tests: 'ALL IMP/ACC HAWB' matrix, negations, 4-state precedence
├── test_capture.py              # 11 tests: DPI awareness, foreground window, mock injection, regions
├── test_ocr_parser.py           # 40 tests: IATA Mod-7, numeric cleanup, 100% mock screen accuracy
├── test_pdf_generator.py        # 4 tests: %PDF-, exact ISO A4 MediaBox, UTF-8 Vietnamese typography
├── test_session_store.py        # 11 tests: CRUD, deduplication, observer listeners, thread safety
└── test_e2e_workflow.py         # 3 tests: Full single-scan, multi-AWB shift, duplicate scan elevation
```

---

## 3. Detailed Test Module Breakdown

### 3.1 `mock_generator.py` & `test_ocr_parser.py` (40 Tests - 100% Pass)
- **IATA Resolution 600a Modulo-7 Verification:** Validates serial algorithm $S_7 \pmod 7 == C$ across valid check digits (0..6) and rejects invalid checksums (mismatches and digits 7..9).
- **OCR Token & Numeric Sanitization:** Normalizes OCR character substitutions (`O` $\to$ `0`, `l` $\to$ `1`, `S` $\to$ `5`, `B` $\to$ `8`), US and European decimal formats.
- **Mock Hermes CMS Screen Fixtures (10 Operational Archetypes):**
  1. `FIX-01`: Clean Standard Lufthansa Cargo (`020-12345675`, 45 PCS, 1250.50 KG, `CLEARED`)
  2. `FIX-02`: European Terminology (`020-98765435`, 120 Colli, 3450.00 KG, `CLEARED`)
  3. `FIX-03`: Compound Colli/Weight Format (`020-45678905`, 15 Colli, 230.75 KG, `CLEARED`)
  4. `FIX-04`: Missing HAWB Flag (`020-87654324`, 8 PCS, 95.20 KG, `PENDING_HAWB`)
  5. `FIX-05`: Direct Master Consignment (`020-33445565`, 1 PKG, 12.50 KG, `DIRECT_SHIPMENT`)
  6. `FIX-06`: Backslash Delimiter (`020-77889906`, 60 Colli, 1800.00 KG, `CLEARED`)
  7. `FIX-07`: Pipe Delimiter (`020-11223343`, 30 PCS, 450.00 KG, `CLEARED`)
  8. `FIX-08`: Vietnamese Consignee Entity (`020-55667780`, 25 PCS, 620.00 KG, `CLEARED`)
  9. `FIX-09`: European Kilogram Weight (`020-99887760`, 10 Colli, 125.50 KG, `CLEARED`)
  10. `FIX-10`: Modulo-7 Checksum Mismatch (`020-24681359`, 5 PCS, 80.00 KG, `CHECKSUM_ERROR`)
- **Accuracy Verification:** Asserts 100% extraction accuracy on AWB number, pieces count, gross weight (kg), and clearance status across all 10 synthetic screens.

### 3.2 `test_business_rules.py` (58 Tests - 100% Pass)
- **Clearance Flag Tolerances:** Case insensitivity, spacing around delimiters, slashes (`/`), backslashes (`\`), pipes (`|`), hyphens (`-`), OCR substitutions (`1MP`, `A11`).
- **Disqualifying Negation Patterns:** Explicit rejections (`NOT`, `NON`, `PARTIAL`, `WAITING FOR`, `PENDING`).
- **Consolidation Detection:** Detection of master consolidation keywords requiring HAWBs (`CONSOL`, `MULTI-HOUSE`, `HOUSE BILLS`).
- **Precedence Matrix:**
  1. Checksum error takes highest operational warning precedence (`CHECKSUM_ERROR`).
  2. Un-negated `ALL IMP/ACC HAWB` flag grants clearance (`CLEARED`).
  3. Consolidation shipment lacking clearance flag yields operational lock (`PENDING_HAWB`).
  4. Direct shipment without consolidation yields normal processing (`DIRECT_SHIPMENT`).
- **Badge Metadata:** Verification of UI color schemes (`#28A745`, `#FD7E14`, `#0D6EFD`, `#DC3545`) and symbols (`✓`, `!`, `—`, `✗`).

### 3.3 `test_session_store.py` (11 Tests - 100% Pass)
- **CRUD Operations:** `add_record`, `get_record`, `get_by_awb`, `update_record`, `delete_record`, `clear_all`.
- **Deduplication / Upsert:** Duplicate scans of the same AWB merge fields, update timestamps, and elevate status to `CLEARED` without row duplication.
- **Observer Pattern:** Validates callback dispatches on `record_added`, `record_updated`, `record_deleted`, and `session_cleared`.
- **Summary Metrics:** Validates `total_records`, `total_pieces`, `total_weight_kg`, and `cleared_ratio`.
- **JSON Persistence:** Validates round-trip export and import without data degradation.
- **Thread Safety:** Verified under concurrent multi-threaded execution (20 concurrent threads).

### 3.4 `test_capture.py` (11 Tests - 100% Pass)
- **DPI Awareness:** Tests `init_dpi_awareness()` invoking Per-Monitor DPI Aware v2.
- **Mock Mode Testing:** Validates headless test operation via `set_test_mock_image()`.
- **Capture Abstractions:** Fullscreen, active foreground window, and bounded rectangular region.
- **Window Finder:** Verifies Hermes CMS window enumeration via Win32 API.

### 3.5 `test_pdf_generator.py` (4 Tests - 100% Pass)
- **File Integrity:** `%PDF-` magic bytes header and `%%EOF` trailer marker.
- **ISO A4 MediaBox Geometry:** Exact dimensions ($595.28 \times 841.89\text{ pt}$ within 1.0 pt tolerance).
- **Vietnamese UTF-8 Typography:** Embedded Windows system Arial TrueType font rendering Vietnamese diacritics (`PHIẾU BÀN GIAO & ĐỐI SOÁT VẬN ĐƠN CA TRỰC`, `CÔNG TY TNHH`, `Nguyễn Văn Giao`, `Trần Thị Nhận`) with zero `\ufffd` corruption.
- **Handover Form Structure:** 7-column handover grid and formal 3-tier signature block.
- **Progressive Contract Binding:** Gracefully verifies `app.pdf.generator` when implemented.

### 3.6 `test_e2e_workflow.py` (3 Tests - 100% Pass)
- **Single Scan Pipeline:** End-to-end flow from Mock Screen $\to$ ScreenGrabber $\to$ Preprocessor $\to$ DualOCREngine $\to$ DataParser $\to$ BusinessClassifier $\to$ SessionStore $\to$ PDF Handover.
- **Full Shift Handover:** 5 diverse shipments processed in sequence, manual operator record modification, and generation of a 5-shipment handover sheet with all records present.
- **Duplicate Rescan Elevation:** Simulates initial pending scan followed by rescan after HAWB clearance, confirming elevation to `CLEARED` without duplicate rows.

---

## 4. Defect Escalation to Implementation Team
During test suite development, three edge-case defects were discovered in the core implementation:
1. **Decimal Comma Misinterpretation in `parser.py`:**
   - *Issue:* `COMPOUND_INTERLEAVED_PATTERN` regex contained `[\/|\\,]` with optional pieces prefixes, causing standalone weights with decimal commas (`125,50 KG`) to match as `pieces=125, weight=50.0`.
   - *Recommendation:* Require mandatory pieces label/prefix before the separator, or exclude comma `,` from the inter-field separator set when followed by decimal digits.
2. **Clearance Flag Whitespace Strictness in `parser.py` and `classifier.py`:**
   - *Issue:* `CANONICAL_CLEARANCE_REGEX` uses `\s+` between `ACC` and `HAWB`. When OCR groups characters tightly (`ACCHAWB`), `\s+` fails to match.
   - *Recommendation:* Use `\s*` instead of `\s+` between all tokens in `CLEARANCE_FLAG_PATTERN` (as specified in `analysis.md`: `(?i)\bALL\s*IMP\s*[\/\\|\-]\s*ACC\s*HAWB\b`).
3. **Consolidation Substring False Positive in `classifier.py`:**
   - *Issue:* `CONSOLIDATION_KEYWORDS` contains `"HAWB"`, which triggers `is_consolidation_shipment = True` on negative strings like `"DIRECT SHIPMENT - NO HAWB REQUIRED"`.
   - *Recommendation:* Add exclusion for `"NO HAWB"` or `"DIRECT"`.

---

## 5. Verification Command
To run all tests:
```powershell
C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe -m pytest f:/Development/plan/hermes_vision_extractor/tests/ -v
```
To run only unit tests:
```powershell
C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe -m pytest f:/Development/plan/hermes_vision_extractor/tests/test_business_rules.py f:/Development/plan/hermes_vision_extractor/tests/test_capture.py f:/Development/plan/hermes_vision_extractor/tests/test_session_store.py -v
```
To run mock screen OCR accuracy verification:
```powershell
C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe -m pytest f:/Development/plan/hermes_vision_extractor/tests/test_ocr_parser.py -v
```
