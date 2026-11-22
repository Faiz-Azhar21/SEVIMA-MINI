"""Pengujian endpoint Payment Webhook menggunakan perintah `curl` nyata + HMAC-SHA256.

Cocok dijalankan di Windows/Linux/macOS tanpa terpengaruh PowerShell ExecutionPolicy:
    python scripts/test_webhook_curl.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from urllib.request import urlopen


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    secret = os.getenv("WEBHOOK_SECRET", "spp-webhook-secret-2026")
    curl_bin = shutil.which("curl.exe") or shutil.which("curl") or "curl"

    # Ambil tagihan berstatus 'unpaid' pertama dari API
    with urlopen(f"{base_url}/api/billings?status=unpaid", timeout=5) as resp:
        unpaid_list = json.loads(resp.read().decode("utf-8"))

    if not unpaid_list:
        print("Tidak ada tagihan berstatus 'unpaid' untuk diuji.")
        sys.exit(1)

    target = unpaid_list[0]
    tx_id = f"CURL-TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    payload = {
        "transaction_id": tx_id,
        "billing_id": target["id"],
        "amount": target["remaining_amount"],
        "status": "paid",
        "payment_method": "VA_BCA",
    }
    raw_body = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()

    print(
        f"Target billing: ID={target['id']} ({target['billing_code']}) | "
        f"NIM={target['nim']} | Sisa=Rp {target['remaining_amount']:,}"
    )

    print("\n1) Uji curl dengan signature INVALID (harus HTTP 401):")
    r_invalid = subprocess.run(
        [
            curl_bin,
            "-s",
            "-i",
            "-X",
            "POST",
            f"{base_url}/api/webhook/payment",
            "-H",
            "Content-Type: application/json",
            "-H",
            "X-Signature: invalid-signature-123",
            "-d",
            raw_body,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    print(r_invalid.stdout)

    print("2) Uji curl dengan signature VALID HMAC-SHA256 (harus HTTP 200 OK & unpaid -> paid):")
    print(f"X-Signature: {signature}")
    r_valid = subprocess.run(
        [
            curl_bin,
            "-s",
            "-i",
            "-X",
            "POST",
            f"{base_url}/api/webhook/payment",
            "-H",
            "Content-Type: application/json",
            "-H",
            f"X-Signature: {signature}",
            "-d",
            raw_body,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    print(r_valid.stdout)


if __name__ == "__main__":
    main()
