#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
BILLING_ID="${2:-31}"
AMOUNT="${3:-5000000}"
SECRET="${WEBHOOK_SECRET:-spp-webhook-secret-2026}"

TX_ID="CURL-TRX-$(date +%Y%m%d%H%M%S)"
PAYLOAD="{\"transaction_id\":\"${TX_ID}\",\"billing_id\":${BILLING_ID},\"amount\":${AMOUNT},\"status\":\"paid\",\"payment_method\":\"VA_BCA\"}"
SIGNATURE=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

echo "=== 1) Test invalid signature (expect 401) ==="
curl -s -i -X POST "${BASE_URL}/api/webhook/payment" \
  -H "Content-Type: application/json" \
  -H "X-Signature: invalid-signature" \
  -d "${PAYLOAD}"

echo -e "\n\n=== 2) Test valid HMAC-SHA256 signature (expect 200 OK) ==="
echo "X-Signature: ${SIGNATURE}"
curl -s -i -X POST "${BASE_URL}/api/webhook/payment" \
  -H "Content-Type: application/json" \
  -H "X-Signature: ${SIGNATURE}" \
  -d "${PAYLOAD}"
echo ""
