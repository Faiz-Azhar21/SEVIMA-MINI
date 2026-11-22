param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$BillingId = 0,
    [int]$Amount = 5000000,
    [string]$Secret = "spp-webhook-secret-2026"
)

# Jika BillingId tidak diisi, cari tagihan berstatus 'unpaid' pertama dari API
if ($BillingId -eq 0) {
    $unpaid = Invoke-RestMethod -Uri "$BaseUrl/api/billings?status=unpaid" -Method Get
    if ($unpaid.Count -eq 0) {
        Write-Host "Tidak ada tagihan berstatus 'unpaid'. Sertakan parameter -BillingId secara manual." -ForegroundColor Yellow
        exit 1
    }
    $BillingId = $unpaid[0].id
    $Amount = $unpaid[0].remaining_amount
    Write-Host "Target tagihan otomatis: ID=$BillingId ($($unpaid[0].billing_code)) | Sisa=Rp $Amount" -ForegroundColor Cyan
}

$txId = "CURL-TRX-" + (Get-Date -Format "yyyyMMddHHmmss")
$payload = "{`"transaction_id`":`"$txId`",`"billing_id`":$BillingId,`"amount`":$Amount,`"status`":`"paid`",`"payment_method`":`"VA_BCA`"}"

# Hitung signature HMAC-SHA256
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($Secret)
$hashBytes = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($payload))
$signature = ([System.BitConverter]::ToString($hashBytes) -replace "-", "").ToLower()

Write-Host "`n1) Menguji webhook dengan signature INVALID (harus ditolak 401)..." -ForegroundColor Yellow
curl.exe -s -i -X POST "$BaseUrl/api/webhook/payment" `
  -H "Content-Type: application/json" `
  -H "X-Signature: invalid-signature-123" `
  -d $payload

Write-Host "`n`n2) Menguji webhook dengan signature VALID (harus 200 OK & status unpaid -> paid)..." -ForegroundColor Green
Write-Host "X-Signature: $signature"
curl.exe -s -i -X POST "$BaseUrl/api/webhook/payment" `
  -H "Content-Type: application/json" `
  -H "X-Signature: $signature" `
  -d $payload
Write-Host ""
