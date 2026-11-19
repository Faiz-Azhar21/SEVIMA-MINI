import threading
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.calon_mahasiswa import CalonMahasiswa

# Reentrant lock to prevent deadlocks when generate_nim is called within an outer locked block
_nim_lock = threading.RLock()

def generate_nim(tahun: int, kode_prodi: str, db: Session) -> str:
    """
    Generate NIM format: YYYY[KODE]XXXX
    Example: 2025001-0001
    
    Thread-safe implementation using reentrant lock (RLock) and database querying
    to prevent race conditions in concurrent request environments.
    """
    clean_kode = str(kode_prodi).strip().zfill(3)
    prefix = f"{tahun}{clean_kode}-"

    with _nim_lock:
        # Query the highest NIM with the current year & prodi prefix
        last_nim_row = (
            db.query(CalonMahasiswa.nim)
            .filter(CalonMahasiswa.nim.like(f"{prefix}%"))
            .order_by(CalonMahasiswa.nim.desc())
            .first()
        )

        if last_nim_row and last_nim_row[0]:
            try:
                parts = last_nim_row[0].split("-")
                current_seq = int(parts[1])
                next_seq = current_seq + 1
            except (IndexError, ValueError):
                count = (
                    db.query(CalonMahasiswa)
                    .filter(CalonMahasiswa.nim.like(f"{prefix}%"))
                    .count()
                )
                next_seq = count + 1
        else:
            next_seq = 1

        nim = f"{prefix}{next_seq:04d}"
        return nim
