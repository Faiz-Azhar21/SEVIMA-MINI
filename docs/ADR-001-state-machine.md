# ADR-001: Implementasi State Machine KRS Menggunakan Tabel Transisi Sendiri

- **Status**: Accepted
- **Tanggal**: 2026-11-20
- **Modul**: SEVIMA-Mini — Modul KRS (Minggu 6)

## Konteks
Dokumen tugas Minggu 5–6 mencantumkan *state management library* pada bagian tools untuk menegakkan siklus hidup status KRS (`DRAFT`, `SUBMITTED`, `APPROVED`, `REVISION`). Kita perlu memutuskan apakah akan menggunakan library pihak ketiga (`python-statemachine` atau `transitions`) atau membangun tabel transisi eksplisit sendiri menggunakan Python `Enum` dan `dict`.

## Opsi yang Dipertimbangkan

| Kriteria | Tabel Transisi Sendiri (`dict`) | Library (`python-statemachine` / `transitions`) |
| :--- | :--- | :--- |
| **Dependensi** | Tidak ada (pure Python stdlib) | +1 paket eksternal |
| **Kompleksitas (4 state, 4 transisi)** | Cukup, ringkas (~20 baris), eksplisit | Berlebihan (*overkill*) untuk 4 panah |
| **Integrasi dengan Aktor (`(state, actor)`)** | Langsung menjadi kunci tuple pada dictionary | Memerlukan tambahan *guard* / *callback* |
| **Pemisahan `cek_transisi()` vs `transition()`** | Sangat mudah untuk *fail-fast* sebelum validasi mahal | Perlu penyesuaian hook internal |
| **Kemudahan Pengujian & Viva** | Sangat mudah diaudit & dijelaskan baris per baris | Harus memahami mekanisme internal library |
| **Skalabilitas State Banyak + Callback** | Mulai merepotkan jika > 8 state & banyak side-effect | Sangat layak (ada hook on_enter/on_exit & diagram otomatis) |

## Keputusan
Memilih **Tabel Transisi Sendiri** (`TRANSITIONS: dict[tuple[KRSStatus, Actor], set[KRSStatus]]` di `app/state_machine.py`) dipadukan dengan dua method terenkapsulasi pada model `KRS`:
1. `cek_transisi(target, actor)` — memeriksa keabsahan transisi tanpa mengubah state (melempar `TransitionError` HTTP `409`).
2. `transition(target, actor)` — satu-satunya pintu yang diizinkan mengubah `self.status`.

## Konsekuensi
- **Positif**:
  - Tidak menambah dependensi eksternal dan tidak menimbulkan konflik dengan SQLAlchemy ORM (`version_id_col` dan mapped enum bekerja langsung).
  - Prinsip *default deny*: pasangan `(status, aktor)` yang tidak tertulis otomatis menghasilkan `set()` sehingga transisi ilegal (`DRAFT → APPROVED`, `APPROVED → *`, dll.) mustahil lolos.
  - Mudah diuji secara menyeluruh (32 kombinasi `itertools.product` di `tests/test_state_machine.py`) dan mudah dijelaskan saat Viva.
- **Negatif / Rencana Migrasi**:
  - Jika pada iterasi mendatang siklus KRS berkembang memiliki banyak status baru (mis. `CANCELLED`, `LOCKED_BY_DEADLINE`, `CHANGE_PERIOD`, `WAITLIST`) dengan *callback* kompleks pada tiap perpindahan, desain ini dapat direfaktor ke `python-statemachine` tanpa mengubah kontrak service maupun API karena seluruh logika transisi sudah terenkapsulasi di dalam method `KRS.transition()`.
