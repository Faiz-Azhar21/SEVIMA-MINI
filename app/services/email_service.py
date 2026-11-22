"""Service pengiriman email kuitansi (receipt) dan reminder tunggakan SPP.

Mendukung pengiriman SMTP asli jika env SMTP_HOST dikonfigurasi; jika tidak,
berjalan dalam mode simulasi yang menyimpan HTML receipt ke folder `receipts/`
serta mencatat seluruh log ke tabel `email_log`.
"""

from __future__ import annotations

import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import RECEIPTS_DIR, SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER
from app.models import Billing, EmailLog, Mahasiswa, Payment


def format_rupiah(amount: int | float) -> str:
    """Format angka integer menjadi string Rupiah (contoh: Rp 5.000.000)."""
    return f"Rp {int(round(amount)):,}".replace(",", ".")


def _send_via_smtp(recipient: str, subject: str, html_body: str, text_body: str) -> tuple[bool, str]:
    if not SMTP_HOST:
        return False, "simulated"

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True, "sent_smtp"
    except Exception:
        return False, "simulated"


def send_payment_receipt(
    db: Session,
    mahasiswa: Mahasiswa,
    billing: Billing,
    payment: Payment,
    payment_method_name: str,
    receipts_dir: Path | None = None,
) -> EmailLog:
    """Kirim email kuitansi pembayaran dan simpan file HTML receipt + log database."""
    target_dir = receipts_dir or RECEIPTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    subject = f"[Kuitansi SPP] Pembayaran {billing.billing_code} - {payment.transaction_id}"
    paid_str = payment.paid_at.strftime("%d %B %Y %H:%M WIB")
    remaining = max(0, billing.total_amount - billing.paid_amount)

    text_body = (
        f"Halo {mahasiswa.nama} (NIM: {mahasiswa.nim}),\n\n"
        f"Pembayaran SPP Anda telah kami terima.\n"
        f"- Kode Tagihan   : {billing.billing_code}\n"
        f"- Semester       : {billing.semester}\n"
        f"- ID Transaksi   : {payment.transaction_id}\n"
        f"- Metode         : {payment_method_name}\n"
        f"- Nominal Bayar  : {format_rupiah(payment.amount)}\n"
        f"- Total Terbayar : {format_rupiah(billing.paid_amount)} / {format_rupiah(billing.total_amount)}\n"
        f"- Sisa Tagihan   : {format_rupiah(remaining)}\n"
        f"- Status Billing : {billing.status.upper()}\n"
        f"- Waktu Bayar    : {paid_str}\n\n"
        f"Terima kasih,\nBagian Keuangan Akademik"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8" />
  <title>{subject}</title>
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6fb; padding: 24px; color: #1e293b; }}
    .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 28px; box-shadow: 0 4px 18px rgba(15,23,42,0.08); }}
    .badge {{ display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 700; background: #dcfce7; color: #166534; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
    td {{ padding: 10px 4px; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
    td.label {{ color: #64748b; width: 42%; }}
    td.val {{ font-weight: 600; text-align: right; }}
    .footer {{ margin-top: 20px; font-size: 12px; color: #64748b; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <h2 style="margin:0 0 6px;">Kuitansi Pembayaran SPP</h2>
    <span class="badge">STATUS: {billing.status.upper()}</span>
    <p style="margin-top:16px;">Halo <strong>{mahasiswa.nama}</strong> ({mahasiswa.nim} - {mahasiswa.program_studi}), pembayaran Anda telah berhasil diproses.</p>
    <table>
      <tr><td class="label">Kode Tagihan</td><td class="val">{billing.billing_code}</td></tr>
      <tr><td class="label">Semester</td><td class="val">{billing.semester}</td></tr>
      <tr><td class="label">ID Transaksi</td><td class="val">{payment.transaction_id}</td></tr>
      <tr><td class="label">Metode Pembayaran</td><td class="val">{payment_method_name}</td></tr>
      <tr><td class="label">Jumlah Dibayar</td><td class="val">{format_rupiah(payment.amount)}</td></tr>
      <tr><td class="label">Total Tagihan (termasuk denda)</td><td class="val">{format_rupiah(billing.total_amount)}</td></tr>
      <tr><td class="label">Total Terbayar</td><td class="val">{format_rupiah(billing.paid_amount)}</td></tr>
      <tr><td class="label">Sisa Tagihan</td><td class="val">{format_rupiah(remaining)}</td></tr>
      <tr><td class="label">Waktu Pembayaran</td><td class="val">{paid_str}</td></tr>
    </table>
    <div class="footer">Email ini dikirim otomatis oleh Sistem Keuangan SPP Kampus.</div>
  </div>
</body>
</html>
"""

    safe_tx = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in payment.transaction_id)
    receipt_file = target_dir / f"receipt_{safe_tx}.html"
    receipt_file.write_text(html_body, encoding="utf-8")

    _, delivery_status = _send_via_smtp(mahasiswa.email, subject, html_body, text_body)

    log = EmailLog(
        mahasiswa_id=mahasiswa.id,
        billing_id=billing.id,
        recipient_email=mahasiswa.email,
        email_type="receipt",
        subject=subject,
        body=text_body,
        delivery_status=delivery_status,
        receipt_file_path=str(receipt_file),
        sent_at=datetime.now(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def send_payment_reminder(
    db: Session,
    mahasiswa: Mahasiswa,
    billing: Billing,
    reason: str = "Mendekati jatuh tempo",
) -> EmailLog:
    """Kirim email reminder otomatis untuk tagihan SPP yang belum lunas / overdue."""
    remaining = max(0, billing.total_amount - billing.paid_amount)
    subject = f"[Reminder SPP] Tagihan {billing.billing_code} ({billing.status.upper()})"
    text_body = (
        f"Halo {mahasiswa.nama} (NIM: {mahasiswa.nim}),\n\n"
        f"Pengingat pembayaran SPP ({reason}):\n"
        f"- Kode Tagihan : {billing.billing_code}\n"
        f"- Semester     : {billing.semester}\n"
        f"- Jatuh Tempo  : {billing.due_date.isoformat()}\n"
        f"- Total Tagihan: {format_rupiah(billing.total_amount)} (Denda: {format_rupiah(billing.penalty_amount)})\n"
        f"- Sisa Tagihan : {format_rupiah(remaining)}\n"
        f"- Status       : {billing.status.upper()}\n\n"
        f"Mohon segera melakukan pembayaran agar akses pengisian KRS tidak terblokir.\n"
        f"Bagian Keuangan Akademik"
    )
    html_body = f"<pre style='font-family:Segoe UI,Arial,sans-serif;'>{text_body}</pre>"

    _, delivery_status = _send_via_smtp(mahasiswa.email, subject, html_body, text_body)

    log = EmailLog(
        mahasiswa_id=mahasiswa.id,
        billing_id=billing.id,
        recipient_email=mahasiswa.email,
        email_type="reminder",
        subject=subject,
        body=text_body,
        delivery_status=delivery_status,
        receipt_file_path=None,
        sent_at=datetime.now(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
