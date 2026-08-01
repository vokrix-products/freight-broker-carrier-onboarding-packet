import sys
from processor import process_file

def main():
    # Hardcoded CSV representing a complete carrier packet
    test_bytes = (
        b"CarrierName,DOT,MC,InsuranceExpiry,W9,SignedContract\n"
        b"Acme Trucking,123456,MC-789012,2026-12-31,Yes,Yes"
    )
    results = process_file(test_bytes)
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    first = results[0]
    assert first["title"] == "Acme Trucking", f"Unexpected title: {first['title']}"
    assert first["status"] == "complete:good", f"Unexpected status: {first['status']}"
    print("Demo successful. Result:", first)
    sys.exit(0)

if __name__ == "__main__":
    main()
