import os, time, json, socket, requests, sys
sys.path.insert(0, 'backend')

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
PRODUCT_ID = os.environ["PRODUCT_ID"]

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

# Printed once at boot so the logs answer "is this container's DNS working"
# and "which product am I polling" without guessing.
def _startup_diagnostics():
    host = SUPABASE_URL.split("//")[-1].split("/")[0]
    try:
        ip = socket.gethostbyname(host)
        print(f"startup: resolved {host} -> {ip}", flush=True)
    except Exception as e:
        print(f"startup: DNS FAILED for {host}: {e}", flush=True)
    print(f"startup: product_id={PRODUCT_ID} host={host} code=poller-a3740eb+", flush=True)

_startup_diagnostics()

def poll_jobs():
    url = f"{SUPABASE_URL}/rest/v1/jobs?select=*&status=eq.pending&job_type=eq.process_upload&product_id=eq.{PRODUCT_ID}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def download_file(bucket, path):
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    r = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY}, timeout=120)
    r.raise_for_status()
    return r.content

def upload_file(bucket, path, data):
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    r = requests.put(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY}, data=data, timeout=120)
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
    r = requests.patch(url, headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()

def write_records(records):
    url = f"{SUPABASE_URL}/rest/v1/records"
    r = requests.post(url, headers=HEADERS, json=records, timeout=60)
    r.raise_for_status()

from processor import process_file

# A network blip used to raise straight out of the loop and kill the container,
# which then crash-looped. Poll failures are now logged and retried instead.
while True:
    try:
        jobs = poll_jobs()
    except Exception as e:
        print(f"poll failed: {e}", flush=True)
        time.sleep(30)
        continue

    if jobs:
        print(f"Processing {len(jobs)} job(s)", flush=True)
        for job in jobs:
            try:
                # download input file
                content = download_file("uploads", job["input_file_path"])
                # run processor
                result = process_file(content)  # processor returns list of record dicts
                # upload result file
                result_data = json.dumps(result).encode()
                output_path = f"{job['id']}.json"
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
                        "source_file_path": job["input_file_path"],
                        "due_date": rec.get("due_date"),
                    })
                if records:
                    write_records(records)
                update_job(job["id"], "completed", result_summary=f"{len(records)} records processed", output_file_path=output_path)
            except Exception as e:
                print(f"Job {job['id']} failed: {e}", flush=True)
                try:
                    update_job(job["id"], "failed", result_summary=str(e))
                except Exception as e2:
                    print(f"Could not mark job {job['id']} failed: {e2}", flush=True)
    time.sleep(60)
