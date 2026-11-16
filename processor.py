import csv
import datetime
import io
import re

from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter

STATUS_COMPLETE = "complete:good"
STATUS_MISSING_REQUIRED = "missing_required:critical"
STATUS_MISSING_OPTIONAL = "missing_optional:warning"
STATUS_EXPIRED = "expired:critical"

_TRUE_VALUES = {"yes", "true", "1", "y"}

# --- Deterministic PDF text extraction patterns -----------------------------
# No LLM: fields are read straight from the extracted PDF text with regexes.
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_YMD_SLASH_RE = re.compile(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b")
# US packet convention: MM/DD/YYYY. Assumed, not detected.
_MDY_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

_EXPIRY_LABEL_RE = re.compile(
    r"(?:insurance\s+expir\w*|expir\w*\s+date|policy\s+expir\w*"
    r"|expiration(?:\s+date)?|expires?\s+on|expires?)\D{0,40}",
    re.IGNORECASE,
)
_DOT_RE = re.compile(
    r"(?:USDOT|US\s+DOT|DOT)\s*(?:#|No\.?|Number)?\s*[:\-]?\s*(\d{4,8})",
    re.IGNORECASE,
)
_MC_RE = re.compile(
    r"\bMC\s*(?:#|No\.?|Number)?\s*[:\-]?\s*(\d{5,8})\b", re.IGNORECASE
)
_NAME_RE = re.compile(
    r"(?:carrier|company|legal|business)\s+name\s*[:\-]\s*([^\n\r]{2,80})",
    re.IGNORECASE,
)
_W9_RE = re.compile(r"\bW[\s\-]?9\b", re.IGNORECASE)
_SIGNED_RE = re.compile(r"\b(?:signed|signature)\b", re.IGNORECASE)

# Docling loads layout/table/OCR models into memory. Build it once per process.
_converter = None


def _converter_instance():
    global _converter
    if _converter is None:
        _converter = DocumentConverter()
    return _converter


def _pdf_to_text(file_bytes: bytes) -> str:
    """
    Extract text from PDF bytes with Docling (CPU only, Apache 2.0).
    Returns markdown, so tables come back as markdown tables and scanned
    pages are read via Docling's OCR. No LLM.
    """
    source = DocumentStream(name="packet.pdf", stream=io.BytesIO(file_bytes))
    result = _converter_instance().convert(source)
    return result.document.export_to_markdown()


def process_file(file_bytes: bytes) -> list[dict]:
    """
    Process a carrier onboarding packet (PDF or CSV bytes) and return
    a list of dictionaries, one per carrier, with keys:
        title (carrier company name),
        status (one of: complete:good, missing_required:critical,
                missing_optional:warning, expired:critical),
        details (dict of extracted fields),
        due_date (ISO date string or None).
    """
    # Detect PDF vs. CSV
    if file_bytes[:4] == b'%PDF':
        return _process_pdf(file_bytes)
    else:
        return _process_csv(file_bytes)


def _safe_date(year: int, month: int, day: int):
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _parse_first_date(text: str):
    """Return the first parseable date in `text`, or None."""
    if not text:
        return None

    m = _ISO_DATE_RE.search(text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _YMD_SLASH_RE.search(text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _MDY_RE.search(text)
    if m:
        year = int(m.group(3))
        if year < 100:
            year += 2000
        return _safe_date(year, int(m.group(1)), int(m.group(2)))

    return None


def _extract_expiry(text: str):
    """
    Find the insurance expiry date. Only dates that follow an expiry label are
    accepted, so a policy start date or issue date is never mistaken for expiry.
    """
    for match in _EXPIRY_LABEL_RE.finditer(text):
        window = text[match.end():match.end() + 16]
        parsed = _parse_first_date(window)
        if parsed:
            return parsed
    return None


def _fields_from_text(text: str):
    """
    Deterministically extract carrier fields from PDF text.
    Returns (details_dict, expiry_date_or_None).

    Fields that cannot be found come back empty / False, which surfaces the
    packet as incomplete instead of guessing.
    """
    dot_match = _DOT_RE.search(text)
    mc_match = _MC_RE.search(text)
    name_match = _NAME_RE.search(text)
    expiry = _extract_expiry(text)

    details = {
        "carrier_name": name_match.group(1).strip() if name_match else "",
        "dot_number": dot_match.group(1) if dot_match else "",
        "mc_number": f"MC-{mc_match.group(1)}" if mc_match else "",
        "insurance_expiry_date_iso": expiry.isoformat() if expiry else None,
        "has_w9": bool(_W9_RE.search(text)),
        "has_signed_contract": bool(_SIGNED_RE.search(text)),
    }
    return details, expiry


def _status_for(details: dict, expiry_date, today: datetime.date) -> str:
    """Single source of truth for the four status strings. Shared by PDF and CSV."""
    required_ok = all([
        bool(details["carrier_name"]),
        bool(details["dot_number"]),
        bool(details["mc_number"]),
        bool(details["insurance_expiry_date_iso"]),
        bool(details["has_w9"]),
    ])

    if not required_ok:
        return STATUS_MISSING_REQUIRED
    if expiry_date is not None and expiry_date < today:
        return STATUS_EXPIRED
    if not details["has_signed_contract"]:
        return STATUS_MISSING_OPTIONAL
    return STATUS_COMPLETE


def _process_pdf(file_bytes: bytes) -> list[dict]:
    full_text = _pdf_to_text(file_bytes)

    details, expiry = _fields_from_text(full_text)
    status = _status_for(details, expiry, datetime.date.today())

    return [{
        "title": details["carrier_name"],
        "status": status,
        "details": details,
        "due_date": details["insurance_expiry_date_iso"],
    }]


def _process_csv(file_bytes: bytes) -> list[dict]:
    """Process a CSV with columns:
    CarrierName,DOT,MC,InsuranceExpiry,W9,SignedContract,..."""
    text = file_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    results = []
    today = datetime.date.today()

    for row in reader:
        carrier_name = row.get("CarrierName", "").strip()
        dot = row.get("DOT", "").strip()
        mc = row.get("MC", "").strip()
        ins_expiry_str = row.get("InsuranceExpiry", "").strip()
        w9_str = row.get("W9", "").strip().lower()
        signed_str = row.get("SignedContract", "").strip().lower()

        has_ins = bool(ins_expiry_str)
        w9_present = w9_str in _TRUE_VALUES
        signed_present = signed_str in _TRUE_VALUES

        ins_expiry_date = None
        if ins_expiry_str:
            try:
                ins_expiry_date = datetime.date.fromisoformat(ins_expiry_str)
            except ValueError:
                pass

        details = {
            "carrier_name": carrier_name,
            "dot_number": dot,
            "mc_number": mc,
            "insurance_expiry_date_iso": ins_expiry_str if has_ins else None,
            "has_w9": w9_present,
            "has_signed_contract": signed_present,
        }

        results.append({
            "title": carrier_name,
            "status": _status_for(details, ins_expiry_date, today),
            "details": details,
            "due_date": ins_expiry_str if ins_expiry_date else None,
        })
    return results
