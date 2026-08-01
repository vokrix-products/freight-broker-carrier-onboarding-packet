import os, time, json, requests, sys
sys.path.insert(0, 'backend')

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
PRODUCT_ID = os.environ["PRODUCT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

def poll_jobs():
    url = f"{SUPABASE_URL}/rest/v1/jobs?select=*&status=eq.pending&job_type=eq.process_upload&product_id=eq.{PRODUCT_ID}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def download_file(bucket, path):
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    r = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
    r.raise_for_status()
    return r.content

def upload_file(bucket, path, data):
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    r = requests.post(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}, files={"file": data})
    r.raise_for_status()

def update_job(job_id, status, result_summary=None, output_file_path=None):
    url = f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{job_id}"
    payload = {"status": status}
    if result_summary:
        payload["result_summary"] = result_summary
    if output_file_path:
        payload["output_file_path"] = output_file_path
    if status in ("completed", "failed"):
        payload["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    r = requests.patch(url, headers=HEADERS, json=payload)
    r.raise_for_status()

def write_records(records):
    url = f"{SUPABASE_URL}/rest/v1/records"
    r = requests.post(url, headers=HEADERS, json=records)
    r.raise_for_status()

from processor import process

while True:
    jobs = poll_jobs()
    if jobs:
        print(f"Processing {len(jobs)} job(s)")
        for job in jobs:
            try:
                # download input file
                content = download_file("uploads", job["source_file_path"])
                # run processor
                result = process(content)  # processor returns list of record dicts
                # upload result file
                result_data = json.dumps(result).encode()
                output_path = f"results/{job['id']}.json"
                upload_file("results", output_path, result_data)
                # write records
                records = []
                for rec in result:
                    records.append({
                        "product_id": PRODUCT_ID,
                        "customer_id": job.get("customer_id", "default"),
                        "title": rec.get("title", "N/A"),
                        "status": rec.get("status", "unknown"),
                        "details": rec.get("details", {}),
                        "source_file_path": job["source_file_path"],
                        "due_date": rec.get("due_date"),
                    })
                if records:
                    write_records(records)
                update_job(job["id"], "completed", result_summary=f"{len(records)} records processed", output_file_path=output_path)
            except Exception as e:
                print(f"Job {job['id']} failed: {e}")
                update_job(job["id"], "failed", result_summary=str(e))
    time.sleep(60)
