import datetime
import sys

from processor import _fields_from_text, _status_for, process_file


def test_complete():
    csv = (
        b"CarrierName,DOT,MC,InsuranceExpiry,W9,SignedContract\n"
        b"Best Logistics,123,MC-456,2027-06-15,Yes,Yes"
    )
    results = process_file(csv)
    assert len(results) == 1
    assert results[0]["status"] == "complete:good"
    assert results[0]["title"] == "Best Logistics"
    assert results[0]["due_date"] == "2027-06-15"


def test_missing_required():
    csv = (
        b"CarrierName,DOT,MC,InsuranceExpiry,W9,SignedContract\n"
        b"Slow Haulers,,,2026-01-01,No,No"
    )
    results = process_file(csv)
    assert results[0]["status"] == "missing_required:critical"


def test_expired():
    csv = (
        b"CarrierName,DOT,MC,InsuranceExpiry,W9,SignedContract\n"
        b"Expired Inc,111,MC-222,2020-12-31,Yes,Yes"
    )
    results = process_file(csv)
    assert results[0]["status"] == "expired:critical"


def test_missing_optional():
    csv = (
        b"CarrierName,DOT,MC,InsuranceExpiry,W9,SignedContract\n"
        b"Optional Co,333,MC-444,2099-06-01,Yes,No"
    )
    results = process_file(csv)
    assert results[0]["status"] == "missing_optional:warning"


# --- PDF text extraction (deterministic, no LLM) ----------------------------

def test_pdf_text_complete():
    text = (
        "Carrier Onboarding Packet\n"
        "Carrier Name: Best Logistics LLC\n"
        "USDOT Number: 1234567\n"
        "MC Number: 789012\n"
        "Insurance Expiry Date: 2027-06-15\n"
        "W-9 on file. Signed contract received.\n"
    )
    details, expiry = _fields_from_text(text)
    assert details["carrier_name"] == "Best Logistics LLC", details
    assert details["dot_number"] == "1234567", details
    assert details["mc_number"] == "MC-789012", details
    assert details["insurance_expiry_date_iso"] == "2027-06-15", details
    assert details["has_w9"] is True, details
    assert details["has_signed_contract"] is True, details
    assert _status_for(details, expiry, datetime.date(2026, 1, 1)) == "complete:good"


def test_pdf_text_expired():
    text = (
        "Carrier Name: Old Haulers\n"
        "DOT 123456\n"
        "MC-456789\n"
        "Policy Expiration: 12/31/2020\n"
        "W9 and signed.\n"
    )
    details, expiry = _fields_from_text(text)
    assert details["dot_number"] == "123456", details
    assert details["mc_number"] == "MC-456789", details
    assert expiry == datetime.date(2020, 12, 31), expiry
    assert _status_for(details, expiry, datetime.date(2026, 1, 1)) == "expired:critical"


def test_pdf_text_missing_required():
    text = "Carrier Name: Slow Haulers\nInsurance Expiry Date: 2026-01-01\n"
    details, expiry = _fields_from_text(text)
    assert details["dot_number"] == "", details
    assert details["mc_number"] == "", details
    assert details["has_w9"] is False, details
    assert _status_for(details, expiry, datetime.date(2025, 1, 1)) == "missing_required:critical"


def test_pdf_text_runon_line():
    # Regression: Docling can return every field on one line, which used to
    # swallow "DOT Number: ... MC Number: ..." into the carrier name.
    text = (
        "Carrier Name: Apex Logistics LLC DOT Number: 123456 "
        "MC Number: MC-789012 EIN / Tax ID: 47-1234 "
        "Insurance Expiry Date: 2027-06-30 W-9 on file. Signed contract received."
    )
    details, expiry = _fields_from_text(text)
    assert details["carrier_name"] == "Apex Logistics LLC", details
    assert details["dot_number"] == "123456", details
    assert details["mc_number"] == "MC-789012", details
    assert details["insurance_expiry_date_iso"] == "2027-06-30", details
    assert _status_for(details, expiry, datetime.date(2026, 1, 1)) == "complete:good"


def test_docling_importable():
    # Fails loudly if Docling (or a system lib it needs) is not installed.
    from docling.document_converter import DocumentConverter
    assert DocumentConverter is not None


def run_tests():
    tests = [
        test_complete,
        test_missing_required,
        test_expired,
        test_missing_optional,
        test_pdf_text_complete,
        test_pdf_text_expired,
        test_pdf_text_missing_required,
        test_pdf_text_runon_line,
        test_docling_importable,
    ]
    ok = True
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            ok = False
        except Exception as e:
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
            ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run_tests()
