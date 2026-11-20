"""Challenge Opsional (+10%): KRS Recommendation AI.

Menyediakan dua pendekatan sesuai dokumen tugas & video Minggu 6:
1. `CSPRecommendationSolver` (Constraint Satisfaction Problem — Backtracking):
   - Variabel : mata kuliah yang diinginkan mahasiswa (dikelompokkan per kode_induk)
   - Domain   : kelas paralel yang tersedia di database
   - Constraint:
       * Prasyarat terpenuhi (nilai >= C semester sebelumnya)
       * Jadwal tidak bentrok
       * Total SKS <= max_sks (maksimal 24)
       * Prioritas ketat: MK WAJIB > MK PILIHAN, lalu total SKS mendekati ideal
2. `KRSRecommendationAgent` (Function-Calling LLM dengan Guardrail):
   - Mengekspos tool validator deterministik (`cek_bentrok`, `cek_prasyarat`,
     `validate_krs`, `list_kelas_paralel`).
   - Guardrail wajib: LLM dilarang menebak; hasil akhir tetap diputuskan dan
     diverifikasi oleh validator KRS sebelum dikembalikan.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.enums import JenisMK
from app.models import KRSDetail, Matakuliah
from app.queries import get_unmet_prerequisites
from app.validators import (
    MAX_SKS_PER_SEMESTER,
    ConflictValidator,
    DuplicateValidator,
    KRSContext,
    PrerequisiteValidator,
    SKSValidator,
    is_schedule_conflict,
)

GUARDRAIL_SYSTEM_PROMPT = (
    "Anda adalah agen rekomendasi KRS akademik SEVIMA-Mini. "
    "ATURAN KETAT (GUARDRAIL): Jangan berimajinasi atau menebak apakah jadwal bentrok "
    "atau prasyarat terpenuhi. Anda WAJIB memanggil tool `cek_prasyarat`, `cek_bentrok`, "
    "dan `validate_krs` untuk setiap kandidat jadwal. Prioritaskan MK WAJIB di atas MK PILIHAN "
    "dengan total SKS ideal <= 24."
)


@dataclass
class RecommendationResult:
    """Hasil rekomendasi jadwal KRS optimal yang sudah tervalidasi."""

    selected_courses: list[Matakuliah]
    total_sks: int
    wajib_count: int
    pilihan_count: int
    skipped_courses: dict[str, str] = field(default_factory=dict)
    validated: bool = True
    tool_trace: list[str] = field(default_factory=list)


def validate_candidate_schedule(
    db: Session,
    nim: str,
    semester: int,
    courses: list[Matakuliah],
    max_sks: int = MAX_SKS_PER_SEMESTER,
) -> list[str]:
    """Menjalankan seluruh validator nyata pada kombinasi jadwal kandidat.
    Mengembalikan daftar pesan error (kosong = 100% valid).
    """
    errors: list[str] = []
    accepted: list[KRSDetail] = []

    sks_v = SKSValidator(max_sks=max_sks)
    prereq_v = PrerequisiteValidator()
    conflict_v = ConflictValidator()
    dup_v = DuplicateValidator()

    for mk in courses:
        ctx = KRSContext(nim=nim, details=accepted, mk=mk, db=db, semester=semester)
        for validator in (dup_v, sks_v, prereq_v, conflict_v):
            res = validator.validate(ctx)
            if not res.ok:
                errors.append(f"{mk.kode_mk}: {res.message}")
                break
        else:
            accepted.append(KRSDetail(kode_mk=mk.kode_mk, matakuliah=mk))

    return errors


class CSPRecommendationSolver:
    """Constraint Satisfaction Problem (CSP) Backtracking Solver untuk jadwal KRS."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _resolve_domains(
        self,
        nim: str,
        semester: int,
        desired_courses: list[str],
    ) -> tuple[list[tuple[str, list[Matakuliah]]], dict[str, str]]:
        """Memetakan daftar kode MK yang diminta menjadi (variabel, domain kelas paralel)
        dan memfilter MK yang prasyaratnya belum terpenuhi."""
        skipped: dict[str, str] = {}
        grouped: dict[str, list[Matakuliah]] = {}

        for code in desired_courses:
            stmt = select(Matakuliah).where(
                or_(Matakuliah.kode_mk == code, Matakuliah.kode_induk == code)
            )
            sections = list(self.db.execute(stmt).scalars().all())
            if not sections:
                skipped[code] = "Mata kuliah tidak ditemukan"
                continue

            # Kelompokkan berdasarkan kode_induk agar kelas paralel menjadi domain satu variabel
            induk = sections[0].effective_kode_induk
            if induk in grouped:
                continue

            valid_sections: list[Matakuliah] = []
            unmet_reason: Optional[str] = None
            for sec in sorted(sections, key=lambda m: (m.kelas, m.kode_mk)):
                unmet = get_unmet_prerequisites(
                    self.db, nim=nim, kode_mk=sec.kode_mk, semester_sekarang=semester
                )
                if unmet:
                    unmet_reason = (
                        f"Prasyarat tidak terpenuhi: {', '.join(u.nama for u in unmet)}"
                    )
                else:
                    valid_sections.append(sec)

            if not valid_sections:
                skipped[code] = unmet_reason or "Tidak ada kelas yang memenuhi prasyarat"
            else:
                grouped[induk] = valid_sections

        # Urutkan variabel: WAJIB terlebih dahulu, lalu PILIHAN (prioritas wajib > pilihan)
        variables = sorted(
            grouped.items(),
            key=lambda item: (
                0 if item[1][0].jenis == JenisMK.WAJIB else 1,
                -item[1][0].sks,
                item[0],
            ),
        )
        return variables, skipped

    def solve(
        self,
        nim: str,
        desired_courses: list[str],
        semester: int = 2,
        max_sks: int = MAX_SKS_PER_SEMESTER,
        target_sks: int = 20,
    ) -> RecommendationResult:
        """Mencari kombinasi jadwal optimal tanpa bentrok dengan backtracking CSP."""
        variables, skipped = self._resolve_domains(nim, semester, desired_courses)
        n = len(variables)

        # Suffix bound jumlah MK wajib tersisa untuk pruning cepat
        rem_wajib = [0] * (n + 1)
        for i in range(n - 1, -1, -1):
            is_wajib = 1 if variables[i][1][0].jenis == JenisMK.WAJIB else 0
            rem_wajib[i] = rem_wajib[i + 1] + is_wajib

        best_score: tuple[int, int, int, int] = (-1, -10**9, -1, -1)
        best_selection: list[Matakuliah] = []
        current: list[Matakuliah] = []

        def score(sel: list[Matakuliah], total_sks: int, wajib_cnt: int) -> tuple[int, int, int, int]:
            pilihan_cnt = len(sel) - wajib_cnt
            # 1) Maksimalkan jumlah MK WAJIB (prioritas utama)
            # 2) Mendekati target_sks (SKS ideal)
            # 3) Jika jarak sama, pilih total_sks lebih besar
            # 4) Maksimalkan jumlah MK pilihan
            return (wajib_cnt, -abs(total_sks - target_sks), total_sks, pilihan_cnt)

        def backtrack(idx: int, total_sks: int, wajib_cnt: int) -> None:
            nonlocal best_score, best_selection

            # Pruning: bahkan jika semua MK wajib tersisa diambil, tidak bisa mengalahkan best wajib_cnt
            if wajib_cnt + rem_wajib[idx] < best_score[0]:
                return

            if idx == n:
                sc = score(current, total_sks, wajib_cnt)
                if sc > best_score:
                    best_score = sc
                    best_selection = list(current)
                return

            _, domain = variables[idx]
            is_wajib = 1 if domain[0].jenis == JenisMK.WAJIB else 0

            # Coba setiap kelas paralel dalam domain (pilih terlebih dahulu)
            for mk in domain:
                if total_sks + mk.sks > max_sks:
                    continue
                if any(is_schedule_conflict(chosen, mk) for chosen in current):
                    continue
                current.append(mk)
                backtrack(idx + 1, total_sks + mk.sks, wajib_cnt + is_wajib)
                current.pop()

            # Cabang lewati MK ini (jika bentrok atau melebihi batas SKS)
            backtrack(idx + 1, total_sks, wajib_cnt)

        backtrack(0, 0, 0)

        # Catat alasan MK valid yang tidak terpilih (bentrok / melebihi SKS)
        selected_induk = {mk.effective_kode_induk for mk in best_selection}
        for induk, domain in variables:
            if induk not in selected_induk:
                mk_rep = domain[0]
                if sum(m.sks for m in best_selection) + mk_rep.sks > max_sks:
                    skipped[induk] = (
                        f"Tidak dimasukkan agar total SKS tetap <= {max_sks} "
                        f"atau memprioritaskan MK wajib"
                    )
                else:
                    skipped[induk] = (
                        "Tidak ada kelas paralel yang bebas bentrok dengan MK prioritas"
                    )

        # Final guardrail: verifikasi hasil dengan validator nyata
        errors = validate_candidate_schedule(
            self.db, nim=nim, semester=semester, courses=best_selection, max_sks=max_sks
        )
        wajib_count = sum(1 for m in best_selection if m.jenis == JenisMK.WAJIB)
        pilihan_count = len(best_selection) - wajib_count

        return RecommendationResult(
            selected_courses=best_selection,
            total_sks=sum(m.sks for m in best_selection),
            wajib_count=wajib_count,
            pilihan_count=pilihan_count,
            skipped_courses=skipped,
            validated=(len(errors) == 0),
            tool_trace=[
                "csp_resolve_domains(cek_prasyarat)",
                "csp_backtracking(prioritas=WAJIB>PILIHAN)",
                f"validate_krs(valid={len(errors) == 0})",
            ],
        )


class KRSRecommendationAgent:
    """Agen rekomendasi KRS dengan arsitektur Function-Calling LLM + Guardrail Validator.

    AI hanya menyarankan lewat pemanggilan tool (`cek_bentrok`, `cek_prasyarat`,
    `validate_krs`); keputusan akhir tetap ditentukan oleh validator sistem.
    """

    TOOL_SCHEMAS: list[dict[str, Any]] = [
        {
            "name": "cek_prasyarat",
            "description": "Memeriksa apakah mahasiswa sudah memenuhi prasyarat untuk kode_mk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nim": {"type": "string"},
                    "kode_mk": {"type": "string"},
                },
                "required": ["nim", "kode_mk"],
            },
        },
        {
            "name": "cek_bentrok",
            "description": "Memeriksa apakah jadwal dua mata kuliah bentrok.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kode_mk_a": {"type": "string"},
                    "kode_mk_b": {"type": "string"},
                },
                "required": ["kode_mk_a", "kode_mk_b"],
            },
        },
        {
            "name": "validate_krs",
            "description": "Memvalidasi daftar kode_mk usulan terhadap seluruh aturan KRS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nim": {"type": "string"},
                    "daftar_kode_mk": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["nim", "daftar_kode_mk"],
            },
        },
    ]

    def __init__(self, db: Session) -> None:
        self.db = db
        self._csp = CSPRecommendationSolver(db)

    def tool_cek_prasyarat(
        self, nim: str, kode_mk: str, semester: int = 2
    ) -> dict[str, Any]:
        unmet = get_unmet_prerequisites(
            self.db, nim=nim, kode_mk=kode_mk, semester_sekarang=semester
        )
        return {
            "kode_mk": kode_mk,
            "terpenuhi": len(unmet) == 0,
            "belum_terpenuhi": [u.nama for u in unmet],
        }

    def tool_cek_bentrok(self, kode_mk_a: str, kode_mk_b: str) -> dict[str, Any]:
        mk_a = self.db.get(Matakuliah, kode_mk_a)
        mk_b = self.db.get(Matakuliah, kode_mk_b)
        if mk_a is None or mk_b is None:
            return {"bentrok": False, "error": "Mata kuliah tidak ditemukan"}
        return {
            "kode_mk_a": kode_mk_a,
            "kode_mk_b": kode_mk_b,
            "bentrok": is_schedule_conflict(mk_a, mk_b),
        }

    def tool_validate_krs(
        self,
        nim: str,
        daftar_kode_mk: list[str],
        semester: int = 2,
        max_sks: int = MAX_SKS_PER_SEMESTER,
    ) -> dict[str, Any]:
        courses: list[Matakuliah] = []
        errors: list[str] = []
        for code in daftar_kode_mk:
            mk = self.db.get(Matakuliah, code)
            if mk is None:
                errors.append(f"Mata kuliah {code} tidak ditemukan")
            else:
                courses.append(mk)

        errors.extend(
            validate_candidate_schedule(
                self.db, nim=nim, semester=semester, courses=courses, max_sks=max_sks
            )
        )
        return {
            "valid": len(errors) == 0,
            "total_sks": sum(m.sks for m in courses),
            "errors": errors,
        }

    def recommend(
        self,
        nim: str,
        desired_courses: list[str],
        semester: int = 2,
        max_sks: int = MAX_SKS_PER_SEMESTER,
        target_sks: int = 20,
        llm_caller: Optional[
            Callable[[str, dict[str, Callable[..., dict[str, Any]]]], list[str]]
        ] = None,
    ) -> RecommendationResult:
        """Menghasilkan rekomendasi jadwal KRS optimal.

        - Jika `llm_caller` disediakan, agen memberi akses tool validator ke LLM lalu
          memvalidasi usulan LLM secara ketat (guardrail: jika usulan LLM tidak valid,
          ditolak dan digantikan hasil CSP solver yang tervalidasi).
        - Jika `llm_caller` tidak disediakan, langsung memakai CSP backtracking solver.
        """
        if llm_caller is not None:
            trace: list[str] = []

            def wrapped_prereq(kode_mk: str) -> dict[str, Any]:
                trace.append(f"cek_prasyarat({kode_mk})")
                return self.tool_cek_prasyarat(nim, kode_mk, semester=semester)

            def wrapped_bentrok(kode_mk_a: str, kode_mk_b: str) -> dict[str, Any]:
                trace.append(f"cek_bentrok({kode_mk_a}, {kode_mk_b})")
                return self.tool_cek_bentrok(kode_mk_a, kode_mk_b)

            def wrapped_validate(daftar_kode_mk: list[str]) -> dict[str, Any]:
                trace.append(f"validate_krs({daftar_kode_mk})")
                return self.tool_validate_krs(
                    nim, daftar_kode_mk, semester=semester, max_sks=max_sks
                )

            tools = {
                "cek_prasyarat": wrapped_prereq,
                "cek_bentrok": wrapped_bentrok,
                "validate_krs": wrapped_validate,
            }
            proposed_codes = llm_caller(GUARDRAIL_SYSTEM_PROMPT, tools)

            # Guardrail akhir: validator sistem yang memutuskan
            final_check = self.tool_validate_krs(
                nim, proposed_codes, semester=semester, max_sks=max_sks
            )
            trace.append(f"guardrail_final_validate_krs(valid={final_check['valid']})")
            if final_check["valid"]:
                courses = [
                    mk
                    for code in proposed_codes
                    if (mk := self.db.get(Matakuliah, code)) is not None
                ]
                wajib_cnt = sum(1 for m in courses if m.jenis == JenisMK.WAJIB)
                return RecommendationResult(
                    selected_courses=courses,
                    total_sks=sum(m.sks for m in courses),
                    wajib_count=wajib_cnt,
                    pilihan_count=len(courses) - wajib_cnt,
                    skipped_courses={},
                    validated=True,
                    tool_trace=trace,
                )

            # Usulan LLM gagal validasi -> fallback deterministik ke CSP solver
            fallback = self._csp.solve(
                nim=nim,
                desired_courses=desired_courses,
                semester=semester,
                max_sks=max_sks,
                target_sks=target_sks,
            )
            fallback.tool_trace = trace + ["fallback_to_csp"] + fallback.tool_trace
            return fallback

        return self._csp.solve(
            nim=nim,
            desired_courses=desired_courses,
            semester=semester,
            max_sks=max_sks,
            target_sks=target_sks,
        )
