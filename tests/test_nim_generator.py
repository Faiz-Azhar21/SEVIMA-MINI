import concurrent.futures
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker, Session
from app.services.nim_generator import generate_nim, _nim_lock
from app.services.pmb_service import approve_calon_mahasiswa
from app.models.calon_mahasiswa import CalonMahasiswa, StatusPendaftaran

def test_generate_nim_format(test_db: Session):
    tahun = 2025
    kode_prodi = "001"
    nim = generate_nim(tahun=tahun, kode_prodi=kode_prodi, db=test_db)
    assert nim == "2025001-0001"

def test_generate_nim_sequential(test_db: Session):
    tahun = 2025
    kode_prodi = "001"

    # Simulasikan mahasiswa pertama mendapat NIM 2025001-0001
    nim1 = generate_nim(tahun=tahun, kode_prodi=kode_prodi, db=test_db)
    assert nim1 == "2025001-0001"

    calon1 = CalonMahasiswa(
        nama_lengkap="Calon 1",
        email="calon1@test.com",
        phone="081234567890",
        tanggal_lahir=datetime(2005, 1, 1).date(),
        alamat="Alamat 1",
        program_studi_id=1,
        jalur_masuk_id=1,
        status=StatusPendaftaran.APPROVED,
        nim=nim1,
        approved_at=datetime.now(timezone.utc)
    )
    test_db.add(calon1)
    test_db.commit()

    # Generate mahasiswa kedua: harus sequential -0002
    nim2 = generate_nim(tahun=tahun, kode_prodi=kode_prodi, db=test_db)
    assert nim2 == "2025001-0002"

    calon2 = CalonMahasiswa(
        nama_lengkap="Calon 2",
        email="calon2@test.com",
        phone="081234567891",
        tanggal_lahir=datetime(2005, 1, 2).date(),
        alamat="Alamat 2",
        program_studi_id=1,
        jalur_masuk_id=1,
        status=StatusPendaftaran.APPROVED,
        nim=nim2,
        approved_at=datetime.now(timezone.utc)
    )
    test_db.add(calon2)
    test_db.commit()

    # Generate mahasiswa ketiga: harus sequential -0003
    nim3 = generate_nim(tahun=tahun, kode_prodi=kode_prodi, db=test_db)
    assert nim3 == "2025001-0003"

def test_generate_nim_different_prodi(test_db: Session):
    tahun = 2025
    # Generate untuk prodi 001
    nim_prodi_1 = generate_nim(tahun=tahun, kode_prodi="001", db=test_db)
    assert nim_prodi_1 == "2025001-0001"

    # Simpan prodi 001
    calon = CalonMahasiswa(
        nama_lengkap="Calon Prodi 1",
        email="prodi1@test.com",
        phone="081234567890",
        tanggal_lahir=datetime(2005, 1, 1).date(),
        alamat="Alamat 1",
        program_studi_id=1,
        jalur_masuk_id=1,
        status=StatusPendaftaran.APPROVED,
        nim=nim_prodi_1,
        approved_at=datetime.now(timezone.utc)
    )
    test_db.add(calon)
    test_db.commit()

    # Generate untuk prodi 002 (harus mulai dari 0001 juga)
    nim_prodi_2 = generate_nim(tahun=tahun, kode_prodi="002", db=test_db)
    assert nim_prodi_2 == "2025002-0001"

def test_nim_thread_safety_concurrency(test_engine):
    """
    Test thread safety:
    Menguji konkurensi approval menggunakan approve_calon_mahasiswa di multiple thread.
    Memastikan tidak terjadi duplicate NIM ataupun race conditions.
    """
    ThreadSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Pre-populate 10 calon mahasiswa pending
    setup_db = ThreadSession()
    student_ids = []
    for i in range(1, 11):
        calon = CalonMahasiswa(
            nama_lengkap=f"Calon Concurrent {i}",
            email=f"concurrent_{i}@test.com",
            phone=f"0812{i:08d}",
            tanggal_lahir=datetime(2005, 1, 1).date(),
            alamat=f"Alamat {i}",
            program_studi_id=3, # Kode prodi 003
            jalur_masuk_id=1,
            status=StatusPendaftaran.PENDING,
            nim=None,
            created_at=datetime(2025, 5, 1, 10, 0, 0)
        )
        setup_db.add(calon)
        setup_db.flush()
        student_ids.append(calon.id)
    setup_db.commit()
    setup_db.close()

    generated_nims = set()

    def approve_worker(student_id: int):
        session = ThreadSession()
        try:
            approved = approve_calon_mahasiswa(calon_id=student_id, db=session)
            return approved.nim
        finally:
            session.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(approve_worker, sid) for sid in student_ids]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            generated_nims.add(res)

    # 10 calon mahasiswa harus mendapatkan 10 NIM sequential unik tanpa tabrakan
    assert len(generated_nims) == 10
    expected_nims = {f"2025003-{i:04d}" for i in range(1, 11)}
    assert generated_nims == expected_nims
