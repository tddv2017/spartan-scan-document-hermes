"""Hermes CMS Data Parser and Domain Entity Extractor.

Extracts AWB numbers, Pieces (Colli), Gross Weight (kg), Consignee, Agent,
Handling Remarks, Remark Agent, and evaluates the critical 'ALL IMP/ACC HAWB' flag.
Implements strict IATA Resolution 600a Modulo-7 check digit verification.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import DEFAULT_AIRLINE_PREFIX
from app.core.models import ExtractionResult
from app.vision.ocr_engine import OCRResult

logger = logging.getLogger(__name__)


def validate_iata_modulo7(serial: str) -> bool:
    """Validate 8-digit AWB serial number using IATA Resolution 600a Modulo-7 algorithm.

    An AWB serial consists of 7 digits sequential + 1 check digit C:
    C = (7 digits integer) mod 7.
    Since C in [0..6], check digit can never be 7, 8, or 9.
    """
    clean_serial = serial.strip()
    if len(clean_serial) != 8 or not clean_serial.isdigit():
        return False

    s7 = int(clean_serial[:7])
    check_digit = int(clean_serial[7])

    if check_digit > 6:
        return False

    return (s7 % 7) == check_digit


def clean_ocr_digits(s: str) -> str:
    """Normalize common OCR misrecognitions in numeric contexts."""
    trans = str.maketrans({
        "O": "0", "o": "0", "D": "0",
        "I": "1", "l": "1", "|": "1", "!": "1",
        "Z": "2", "z": "2",
        "S": "5", "s": "5",
        "B": "8",
    })
    return s.translate(trans)


def normalize_float(val_str: str) -> Optional[float]:
    """Robust conversion of international number strings (supporting comma/period decimals) to float."""
    if not val_str:
        return None

    cleaned = val_str.strip()
    # Remove any stray spaces or currency/unit symbols
    cleaned = re.sub(r"[^\d.,]", "", cleaned)
    if not cleaned:
        return None

    # Handle European vs US formatting
    if "," in cleaned and "." in cleaned:
        if cleaned.find(".") < cleaned.find(","):
            # Format: 1.250,50 (European thousands period, decimal comma)
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # Format: 1,250.50 (US thousands comma, decimal period)
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Format: 1250,50
        cleaned = cleaned.replace(",", ".")

    try:
        val = float(cleaned)
        return round(val, 2)
    except ValueError:
        return None


class HermesDataParser:
    """Specialized domain parser for Hermes Cargo Management System interface text."""

    # ---------------------------------------------------------------------
    # Regex Specifications
    # ---------------------------------------------------------------------

    # AWB Number: 3-digit prefix + optional delimiters + 8-digit serial (or 4+4 split)
    AWB_PATTERN = re.compile(
        r"(?i)\b(?P<prefix>[0-9OolIZBS]{3})[- \.\/\[\]]*(?P<serial>[0-9OolIZBS]{4}[- ]*[0-9OolIZBS]{4}|[0-9OolIZBS]{8})\b"
    )

    # Compound Pieces & Weight Patterns
    # Dual-label format: 'Colli / Weight: 45 / 1250.50 KG' or 'PCS / WT: 45 / 1250.5 KG'
    COMPOUND_DUAL_LABEL_PATTERN = re.compile(
        r"(?i)(?:colli|pieces?|pcs|pkg|colis)\s*[\/|\\]\s*(?:(?:gross\s*)?w(?:eigh)?t(?:[\s\.]*\(?kg\)?)?)\s*[:=]?\s*(\d+)\s*[\/|\\]\s*(\d+(?:[.,]\d+)?)"
    )

    # Interleaved or compound format: '45 Colli / 1250.50 kg' or 'Colli: 45 / Wt: 1250.50'
    # Comma is strictly excluded as an inter-field delimiter to prevent European decimal comma
    # weights (e.g. '125,50 KG') from falsely matching as pieces=125, weight=50.
    COMPOUND_INTERLEAVED_PATTERN = re.compile(
        r"(?i)(?:colli|pieces?|pcs|pkg|colis)?\s*[:=]?\s*(\d+)\s*(?:colli|pieces?|pcs|pkg|colis)?\s*[\/|\\]\s*(?:(?:gross\s*)?w(?:eigh)?t(?:[\s\.]*\(?kg\)?)?)?\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:kg|kgs|kilos)?"
    )

    # Individual Pieces patterns
    PIECES_LABELED_PATTERN = re.compile(
        r"(?i)\b(?:colli|pieces?|pcs|pkg|colis|total\s+pcs|manifested\s+pcs|recv\s+pcs)\s*[:=\.\-\s]\s*(\d+)\b"
    )
    PIECES_POSTFIX_PATTERN = re.compile(
        r"(?i)\b(\d+)\s*(?:colli|pieces?|pcs|colis)\b"
    )

    # Individual Weight patterns
    WEIGHT_LABELED_PATTERN = re.compile(
        r"(?i)\b(?:gross\s*)?w(?:eigh)?t(?:[\s\.]*\(?kg\)?)?\s*[:=\.\-\s]\s*(\d+(?:[.,]\d+)?)\s*(?:kg|kgs|kilos)?\b"
    )
    WEIGHT_POSTFIX_PATTERN = re.compile(
        r"(?i)\b(\d+(?:[.,]\d+)?)\s*(?:kg|kgs|kilos)\b"
    )

    # Consignee & Agent patterns
    CONSIGNEE_PATTERN = re.compile(
        r"(?i)\b(?:consignee|cnee|deliver\s+to|recipient|to\s+order\s+of)\s*[:\-]\s*([^\r\n]{3,100})"
    )
    AGENT_PATTERN = re.compile(
        r"(?i)\b(?:agent|forwarder|agt|issuing\s+agent|handling\s+agent)\s*[:\-]\s*([^\r\n]{3,100})"
    )

    # Remarks & Remark Agent patterns
    REMARK_AGENT_PATTERN = re.compile(
        r"(?i)\b(?:remark\s+agent|agent\s+remarks?|agt\s+rmk)\s*[:\-]\s*([^\r\n]+)"
    )
    REMARKS_PATTERN = re.compile(
        r"(?i)\b(?:remarks?|handling\s+remarks?|osi|ssr|special\s+remarks?)\s*[:\-]\s*([^\r\n]+)"
    )

    # Critical Business Clearance Flag: ALL IMP/ACC HAWB (supports tightly clustered OCR tokens like ACCHAWB)
    CLEARANCE_FLAG_PATTERN = re.compile(
        r"(?i)\b(?:ALL|A[L1I]{2})\s*(?:IMP|[I1L]MP)\s*[\/\\|\-]\s*(?:ACC|A[C0]{2})\s*(?:HAWB|HAW[B8])\b"
    )
    CLEARANCE_NEGATION_PATTERN = re.compile(
        r"(?i)\b(?:NOT|NON|PARTIAL|UN|WAITING\s+FOR|PENDING)\s+(?:ALL|A[L1I]{2})\s*(?:IMP|[I1L]MP)\s*[\/\\|\-]\s*(?:ACC|A[C0]{2})\s*(?:HAWB|HAW[B8])\b"
    )
    CANONICAL_CLEARANCE_REGEX = CLEARANCE_FLAG_PATTERN

    # ---------------------------------------------------------------------
    # Extraction Methods
    # ---------------------------------------------------------------------

    def extract_awb(self, text: str) -> Tuple[str, str, str, bool]:
        """Extract canonical AWB number, prefix, serial, and Modulo-7 check validity.

        Returns:
            Tuple[str, str, str, bool]: (awb_prefix, awb_serial, awb_number, is_valid_checksum)
        """
        if not text:
            return "", "", "", False

        candidates: List[Tuple[str, str, bool]] = []

        for match in self.AWB_PATTERN.finditer(text):
            p_raw = clean_ocr_digits(match.group("prefix"))
            s_raw = clean_ocr_digits(re.sub(r"[\s\-]", "", match.group("serial")))

            if len(p_raw) == 3 and len(s_raw) == 8 and p_raw.isdigit() and s_raw.isdigit():
                is_valid = validate_iata_modulo7(s_raw)
                candidates.append((p_raw, s_raw, is_valid))

        if not candidates:
            return "", "", "", False

        # Selection priority:
        # 1. Matches Lufthansa prefix (020) and valid Mod-7
        for p, s, valid in candidates:
            if p == DEFAULT_AIRLINE_PREFIX and valid:
                return p, s, f"{p}-{s}", True

        # 2. Any airline prefix with valid Mod-7
        for p, s, valid in candidates:
            if valid:
                return p, s, f"{p}-{s}", True

        # 3. Lufthansa prefix with invalid Mod-7
        for p, s, valid in candidates:
            if p == DEFAULT_AIRLINE_PREFIX:
                return p, s, f"{p}-{s}", False

        # 4. First extracted candidate (marked invalid Mod-7)
        p, s, valid = candidates[0]
        return p, s, f"{p}-{s}", valid

    def extract_pieces_and_weight(self, text: str) -> Tuple[Optional[int], Optional[float]]:
        """Extract Colli/Pieces count and Gross Weight in kg."""
        if not text:
            return None, None

        # Try Dual-label compound pattern first (e.g. 'Colli / Weight: 45 / 1250.50 KG')
        m_dual = self.COMPOUND_DUAL_LABEL_PATTERN.search(text)
        if m_dual:
            try:
                pcs = int(m_dual.group(1))
                wt = normalize_float(m_dual.group(2))
                if pcs >= 0 and wt is not None:
                    return pcs, wt
            except Exception:
                pass

        # Try Interleaved compound pattern (e.g. '45 Colli / 1250.50 KG')
        m_comp = self.COMPOUND_INTERLEAVED_PATTERN.search(text)
        if m_comp:
            try:
                pcs = int(m_comp.group(1))
                wt = normalize_float(m_comp.group(2))
                if pcs >= 0 and wt is not None:
                    return pcs, wt
            except Exception:
                pass

        # Fallback to separate field extractions
        pieces: Optional[int] = None
        weight: Optional[float] = None

        # Pieces extraction
        m_pcs = self.PIECES_LABELED_PATTERN.search(text) or self.PIECES_POSTFIX_PATTERN.search(text)
        if m_pcs:
            try:
                pieces = int(m_pcs.group(1))
            except Exception:
                pass

        # Weight extraction
        m_wt = self.WEIGHT_LABELED_PATTERN.search(text) or self.WEIGHT_POSTFIX_PATTERN.search(text)
        if m_wt:
            weight = normalize_float(m_wt.group(1))

        return pieces, weight

    def extract_consignee(self, text: str) -> str:
        """Extract consignee / recipient company name, cleaning trailing noise."""
        if not text:
            return ""

        match = self.CONSIGNEE_PATTERN.search(text)
        if match:
            raw = match.group(1).strip()
            # Clean common terminal noise (address lines, phone numbers)
            cleaned = re.split(r"(?i)\b(?:address|tel|phone|fax|tax|attn|city)\b", raw)[0]
            cleaned = re.sub(r"[\s\-_:,;]+$", "", cleaned).strip()
            if len(cleaned) >= 3:
                return cleaned

        return ""

    def extract_agent(self, text: str) -> str:
        """Extract freight forwarding agent name."""
        if not text:
            return ""

        match = self.AGENT_PATTERN.search(text)
        if match:
            raw = match.group(1).strip()
            # Clean trailing agent codes (e.g., 37-4-1234 or IATA code)
            cleaned = re.split(r"(?i)\b(?:code|iata|acct|acc|tel|phone)\b", raw)[0]
            cleaned = re.sub(r"[\s\-_:,;]+$", "", cleaned).strip()
            if len(cleaned) >= 2:
                return cleaned

        return ""

    def extract_remarks(self, text: str) -> Tuple[str, str]:
        """Extract general handling remark line and remark agent line.

        Returns:
            Tuple[str, str]: (remark, remark_agent)
        """
        if not text:
            return "", ""

        remark = ""
        remark_agent = ""

        # Extract agent remark
        m_agt_rmk = self.REMARK_AGENT_PATTERN.search(text)
        if m_agt_rmk:
            remark_agent = m_agt_rmk.group(1).strip()

        # Extract general remark
        m_rmk = self.REMARKS_PATTERN.search(text)
        if m_rmk:
            remark = m_rmk.group(1).strip()
        else:
            # Check if clearance flag exists anywhere in text
            flag_match = self.CLEARANCE_FLAG_PATTERN.search(text)
            if flag_match:
                # Capture the surrounding line
                lines = text.splitlines()
                for line in lines:
                    if self.CLEARANCE_FLAG_PATTERN.search(line):
                        remark = line.strip()
                        break

        return remark, remark_agent

    def extract_clearance_flag(self, text: str) -> bool:
        """Evaluate if the authoritative clearance flag 'ALL IMP/ACC HAWB' is present and un-negated."""
        if not text:
            return False

        if self.CLEARANCE_NEGATION_PATTERN.search(text):
            return False

        return bool(self.CLEARANCE_FLAG_PATTERN.search(text))

    # ---------------------------------------------------------------------
    # Top-Level Orchestration
    # ---------------------------------------------------------------------

    def parse(
        self,
        ocr_text: str,
        confidence: float = 1.0,
        tokens: Optional[List[str]] = None,
    ) -> ExtractionResult:
        """Parse raw OCR text and return a validated ExtractionResult."""
        prefix, serial, awb_number, is_valid_chk = self.extract_awb(ocr_text)
        pieces, weight_kg = self.extract_pieces_and_weight(ocr_text)
        consignee = self.extract_consignee(ocr_text)
        agent = self.extract_agent(ocr_text)
        remark, remark_agent = self.extract_remarks(ocr_text)
        has_clearance = self.extract_clearance_flag(ocr_text)

        # If remark was empty but clearance flag was found, populate remark
        if has_clearance and not remark:
            remark = "ALL IMP/ACC HAWB"

        token_list = tokens or [line.strip() for line in ocr_text.splitlines() if line.strip()]

        return ExtractionResult(
            raw_text=ocr_text,
            awb_prefix=prefix,
            awb_serial=serial,
            awb_number=awb_number,
            pieces=pieces,
            weight_kg=weight_kg,
            consignee=consignee,
            agent=agent,
            remark=remark,
            remark_agent=remark_agent,
            has_all_imp_acc_hawb=has_clearance,
            is_valid_checksum=is_valid_chk,
            confidence=round(confidence, 4),
            raw_ocr_tokens=token_list,
        )

    def parse_ocr_result(self, ocr_result: OCRResult) -> ExtractionResult:
        """Parse a structured OCRResult from DualOCREngine."""
        token_strings = [t.text for t in ocr_result.tokens]
        return self.parse(
            ocr_text=ocr_result.full_text,
            confidence=ocr_result.average_confidence,
            tokens=token_strings,
        )
