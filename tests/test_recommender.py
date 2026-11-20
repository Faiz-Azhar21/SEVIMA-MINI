"""Tests untuk Challenge Opsional (+10%): KRS Recommendation AI (CSP + Function-Calling LLM)."""

from app.enums import JenisMK
from app.recommender import (
    CSPRecommendationSolver,
    KRSRecommendationAgent,
    validate_candidate_schedule,
)


def test_csp_memilih_kelas_paralel_dan_prioritas_wajib(db_session, seed_data):
    """Budi (lulus KAL1) meminta BD1(WAJIB Senin 08), PBO1(WAJIB punya kelas B Rabu),
    ML1(PILIHAN Senin 08 bentrok BD1), KAL2(WAJIB), dan AI1(PILIHAN)."""
    solver = CSPRecommendationSolver(db_session)
    res = solver.solve(
        nim="2026002",
        desired_courses=["BD1", "PBO1", "ML1", "KAL2", "AI1"],
        semester=3,
        max_sks=24,
        target_sks=20,
    )

    assert res.validated is True
    assert res.total_sks <= 24
    selected_codes = {m.kode_mk for m in res.selected_courses}
    # Semua MK WAJIB (BD1, PBO1-B, KAL2) harus masuk; ML1 (PILIHAN bentrok BD1) tidak masuk
    assert {"BD1", "PBO1-B", "KAL2", "AI1"} == selected_codes
    assert "ML1" in res.skipped_courses
    assert (
        validate_candidate_schedule(
            db_session, "2026002", 3, res.selected_courses, max_sks=24
        )
        == []
    )


def test_csp_otomatis_lewati_mk_prasyarat_belum_terpenuhi(db_session, seed_data):
    """Rina belum lulus KAL1 -> KAL2 dilewati dengan alasan prasyarat."""
    solver = CSPRecommendationSolver(db_session)
    res = solver.solve(
        nim="2026001",
        desired_courses=["KAL2", "BD1", "ALGO"],
        semester=3,
    )
    assert res.validated is True
    assert "KAL2" not in {m.kode_mk for m in res.selected_courses}
    assert "Prasyarat tidak terpenuhi: Kalkulus I" in res.skipped_courses["KAL2"]
    assert {"BD1", "ALGO"} == {m.kode_mk for m in res.selected_courses}


def test_csp_prioritas_wajib_di_atas_pilihan_saat_sks_terbatas(db_session, seed_data):
    """Jika batas SKS hanya 10, MK WAJIB (BD1=3, ALGO=4, PBO1-B=3 -> total 10)
    wajib diprioritaskan daripada PILIHAN (AI1=3, GAME1=3)."""
    solver = CSPRecommendationSolver(db_session)
    res = solver.solve(
        nim="2026001",
        desired_courses=["AI1", "GAME1", "BD1", "ALGO", "PBO1-B"],
        semester=3,
        max_sks=10,
        target_sks=10,
    )
    assert res.validated is True
    assert res.total_sks == 10
    assert res.wajib_count == 3
    assert all(m.jenis == JenisMK.WAJIB for m in res.selected_courses)


def test_agent_function_calling_llm_valid(db_session, seed_data):
    """Mock LLM yang mengikuti guardrail: memanggil tool validator terlebih dahulu."""
    agent = KRSRecommendationAgent(db_session)

    def mock_llm(_system_prompt, tools):
        assert tools["cek_prasyarat"]("KAL2")["terpenuhi"] is True
        assert tools["cek_bentrok"]("BD1", "PBO1")["bentrok"] is True
        assert tools["cek_bentrok"]("BD1", "PBO1-B")["bentrok"] is False
        kandidat = ["BD1", "PBO1-B", "KAL2"]
        assert tools["validate_krs"](kandidat)["valid"] is True
        return kandidat

    res = agent.recommend(
        nim="2026002",
        desired_courses=["BD1", "PBO1", "KAL2"],
        semester=3,
        llm_caller=mock_llm,
    )
    assert res.validated is True
    assert {m.kode_mk for m in res.selected_courses} == {"BD1", "PBO1-B", "KAL2"}
    assert any(t.startswith("cek_prasyarat") for t in res.tool_trace)
    assert any(t.startswith("cek_bentrok") for t in res.tool_trace)
    assert any(t.startswith("guardrail_final_validate_krs") for t in res.tool_trace)


def test_agent_guardrail_tolak_halusinasi_llm_dan_fallback_csp(db_session, seed_data):
    """Jika LLM berhalusinasi mengusulkan jadwal bentrok/tanpa prasyarat,
    guardrail `validate_krs` menolak dan fallback ke hasil CSP yang valid."""
    agent = KRSRecommendationAgent(db_session)

    def hallucinating_llm(_system_prompt, _tools):
        # Mengusulkan BD1 + PBO1 (bentrok!) dan KAL2 (Rina belum lulus KAL1!)
        return ["BD1", "PBO1", "KAL2"]

    res = agent.recommend(
        nim="2026001",
        desired_courses=["BD1", "PBO1", "KAL2"],
        semester=3,
        llm_caller=hallucinating_llm,
    )
    assert res.validated is True
    assert "fallback_to_csp" in res.tool_trace
    # Fallback CSP memilih BD1 dan PBO1-B (bebas bentrok) serta melewatkan KAL2
    assert {m.kode_mk for m in res.selected_courses} == {"BD1", "PBO1-B"}
