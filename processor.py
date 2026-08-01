import os
import io
import csv
import json
import datetime
import PyPDF2
from openai import OpenAI

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

def _process_pdf(file_bytes: bytes) -> list[dict]:
    # Extract text from PDF
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    full_text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            full_text += page_text + "\n"

    # Construct prompt for DeepSeek extraction
    prompt = (
        "Extract from the following carrier onboarding document text. "
        "Output a single JSON object. The JSON must have exactly these keys:\n"
        '  "title": the carrier company name (the primary entity the buyer tracks),\n'
        '  "status": one of "complete:good", "missing_required:critical", '
        '"missing_optional:warning", "expired:critical",\n'
        '  "details": an object with the extracted fields: carrier_name, '
        'dot_number, mc_number, insurance_expiry_date_iso, has_w9 (boolean), '
        'has_signed_contract (boolean),\n'
        '  "due_date": the insurance expiry date as ISO string (YYYY-MM-DD) or null.\n\n'
        'Required fields for a complete packet: carrier_name, dot_number, mc_number, '
        'insurance_expiry_date_iso, has_w9 (must be true). '
        'If any of those is missing or false, the status must be '
        '"missing_required:critical".\n'
        'If all required fields are present but optional has_signed_contract is '
        'missing or false, status is "missing_optional:warning".\n'
        'If insurance_expiry_date_iso is a date before today, status is '
        '"expired:critical".\n'
        'If everything is present and insurance is not expired, status is '
        '"complete:good".\n\n'
        'Document text:\n' + full_text
    )

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com"
    )
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    content = response.choices[0].message.content.strip()

    # Parse the JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Attempt to extract JSON between triple backticks if present
        import re
        match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            raise ValueError("Failed to parse DeepSeek response as JSON")

    # Ensure required keys
    data.setdefault("details", {})
    data.setdefault("due_date", None)
    return [data]

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

        # Determine presence
        has_carrier = bool(carrier_name)
        has_dot = bool(dot)
        has_mc = bool(mc)
        has_ins = bool(ins_expiry_str)
        w9_present = w9_str in ("yes", "true", "1", "y")
        signed_present = signed_str in ("yes", "true", "1", "y")

        # Parse insurance expiry date
        ins_expiry_date = None
        if ins_expiry_str:
            try:
                ins_expiry_date = datetime.date.fromisoformat(ins_expiry_str)
            except ValueError:
                pass

        # Check required fields
        required_ok = all([has_carrier, has_dot, has_mc, has_ins, w9_present])
        # Check optional
        optional_missing = not signed_present

        # Determine status
        if required_ok:
            if ins_expiry_date and ins_expiry_date < today:
                status = "expired:critical"
            elif optional_missing:
                status = "missing_optional:warning"
            else:
                status = "complete:good"
        else:
            status = "missing_required:critical"

        details = {
            "carrier_name": carrier_name,
            "dot_number": dot,
            "mc_number": mc,
            "insurance_expiry_date_iso": ins_expiry_str if has_ins else None,
            "has_w9": w9_present,
            "has_signed_contract": signed_present
        }

        results.append({
            "title": carrier_name,
            "status": status,
            "details": details,
            "due_date": ins_expiry_str if ins_expiry_date else None
        })
    return results
