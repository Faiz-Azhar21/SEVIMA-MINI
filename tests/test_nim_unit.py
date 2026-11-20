"""Unit test murni untuk format NIM, validasi telepon Indonesia, dan batas counter NIM."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models import NimCounter
from app.schemas import validate_indonesian_phone
from app.services.nim_generator import format_nim, format_nim_display, generate_nim


def test_format_nim_zero_padding() -> None:
    """Arrange-Act-Assert: nomor urut diberi zero-padding 4 digit menjadi 11 digit total."""
    # Arrange
    tahun, kode, nomor = 2025, "001", 7

    # Act
    nim = format_nim(tahun, kode, nomor)

    # Assert
    assert nim == "20250010007"
    assert len(nim) == 11


def test_format_nim_display_with_hyphen() -> None:
    """Helper presentasi memformat NIM 11 digit menjadi tampilan dengan strip."""
    assert format_nim_display("20250010001") == "2025001-0001"

    with pytest.raises(ValueError, match="11 digit"):
        format_nim_display("2025001-0001")


@pytest.mark.parametrize(
    ("tahun", "kode", "nomor"),
    [
        (999, "001", 1),
        (10000, "001", 1),
        (2025, "01", 1),
        (2025, "ABC", 1),
        (2025, "001", 0),
        (2025, "001", 10000),
    ],
)
def test_format_nim_rejects_invalid_inputs(tahun: int, kode: str, nomor: int) -> None:
    with pytest.raises(ValueError):
        format_nim(tahun, kode, nomor)


@pytest.mark.parametrize(
    "phone",
    [
        "08123456789",
        "081234567890",
        "6281234567890",
        "+6281234567890",
        "  085712345678  ",
    ],
)
def test_validate_indonesian_phone_valid(phone: str) -> None:
    result = validate_indonesian_phone(phone)
    assert result == phone.strip()


@pytest.mark.parametrize(
    "phone",
    [
        "12345",
        "07123456789",
        "080123456789",
        "+14155552671",
        "0812-3456-7890",
        "081234567890123456",
        "bukan-nomor",
    ],
)
def test_validate_indonesian_phone_invalid(phone: str) -> None:
    with pytest.raises(ValueError, match="Format nomor telepon Indonesia tidak valid"):
        validate_indonesian_phone(phone)


def test_generate_nim_resets_per_tahun_and_prodi(db: Session) -> None:
    """Counter NIM dihitung terpisah untuk setiap kombinasi (tahun, kode_prodi)."""
    nim_ti_2025_1 = generate_nim(2025, "001", db)
    nim_ti_2025_2 = generate_nim(2025, "001", db)
    nim_si_2025_1 = generate_nim(2025, "002", db)
    nim_ti_2026_1 = generate_nim(2026, "001", db)
    db.commit()

    assert nim_ti_2025_1 == "20250010001"
    assert nim_ti_2025_2 == "20250010002"
    assert nim_si_2025_1 == "20250020001"
    assert nim_ti_2026_1 == "20260010001"


def test_generate_nim_overflow_raises_value_error(db: Session) -> None:
    """Melebihi batas nomor urut 9999 harus melempar ValueError."""
    db.add(NimCounter(tahun=2025, kode_prodi="001", last_number=9999))
    db.commit()

    with pytest.raises(ValueError, match="habis"):
        generate_nim(2025, "001", db)


def test_generate_nim_rejects_invalid_args(db: Session) -> None:
    with pytest.raises(ValueError, match="Tahun"):
        generate_nim(99, "001", db)
    with pytest.raises(ValueError, match="Kode program studi"):
        generate_nim(2025, "12", db)
