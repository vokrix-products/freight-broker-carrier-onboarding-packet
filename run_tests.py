import sys
from processor import process_file

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

def run_tests():
    tests = [
        test_complete,
        test_missing_required,
        test_expired,
        test_missing_optional
    ]
    ok = True
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            ok = False
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    run_tests()
