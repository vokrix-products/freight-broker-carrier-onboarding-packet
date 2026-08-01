# Freight Broker Carrier Onboarding Packet Completeness Checker

Backend extraction service for the **SMB Brokerage Tier** product line. It processes a carrier onboarding document (PDF or CSV) and returns a completeness status for each carrier so the dispatch team can chase missing paperwork before loads are booked.

## Product & Archetype

- **Product:** Carrier onboarding packet completeness checker with a chase incentive — every returned record carries a `status` and a `due_date` so missing or expiring documents surface before they become a problem.
- **Archetype:** SMB brokerage — small freight broker teams onboarding new carriers. The checker classifies each packet into one of four exact statuses:

  - `complete:good` — all required fields present and insurance valid.
  - `missing_required:critical` — a required field is missing or W9 is false.
  - `missing_optional:warning` — all required fields present, but the signed contract is missing.
  - `expired:critical` — insurance expiry date is before today.

## Files

- `processor.py` – Core logic. `process_file(file_bytes: bytes) -> list[dict]` reads PDF bytes (PyPDF2 text extraction + DeepSeek JSON evaluation) or CSV bytes (fast local parsing for testing) and returns one dict per carrier with keys `title`, `status`, `details`, `due_date`.
- `run_demo.py` – Hardcoded demo using a CSV input; exits 0 on success.
- `run_tests.py` – Automated tests covering all four statuses; runs without arguments and exits 0 on success.
- `requirements.txt` – Python dependencies (`openai`, `requests`, `PyPDF2`).

## Poller Input

The poller feeds raw file bytes directly to `process_file(file_bytes: bytes)`.

**PDF input:** text is extracted with PyPDF2 and sent to DeepSeek, which returns a single JSON object with `title`, `status`, `details`, and `due_date`. Requires `DEEPSEEK_API_KEY`.

**CSV columns (for testing):**
```
CarrierName,DOT,MC,InsuranceExpiry,W9,SignedContract
Acme Trucking,123456,MC-789012,2026-12-31,Yes,Yes
```

- `CarrierName` — carrier company name (becomes `title`; required)
- `DOT` — USDOT number (required)
- `MC` — MC number (required)
- `InsuranceExpiry` — ISO date `YYYY-MM-DD` (required)
- `W9` — `Yes/No/True/False/1/0` (required, must be truthy)
- `SignedContract` — `Yes/No/True/False/1/0` (optional)

## Output

`process_file` returns a list of dicts, one per carrier:
- `title` — carrier company name
- `status` — one of the four exact status strings listed above
- `details` — extracted fields: `carrier_name`, `dot_number`, `mc_number`, `insurance_expiry_date_iso`, `has_w9`, `has_signed_contract`
- `due_date` — ISO date string of the insurance expiry, or `None`

## Setup

```bash
pip install -r requirements.txt
export DEEPSEEK_API_KEY="your_key"
python3 run_tests.py
python3 run_demo.py
```

Dashboard: https://freight-broker-carrier-onboarding-packet.vokrix.co
Vercel: freight-broker-carrier-onboarding-packet
Railway: 31ed37a4-5d0e-423d-b868-f1f8fc8a38ed
Railway: freight-broker-carrier-onboarding-packet
Railway: freight-broker-carrier-onboarding-packet
Cloudflare: freight-broker-carrier-onboarding-packet.vokrix.co
