"""FastAPI application untuk Modul KRS SEVIMA-Mini (Minggu 5-6)."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.exceptions import KRSError
from app.recommender import KRSRecommendationAgent
from app.schemas import (
    AddCourseRequest,
    ApproveKRSRequest,
    KRSResponse,
    MatakuliahResponse,
    RecommendRequest,
    RecommendResponse,
    ReviseKRSRequest,
    ValidationResponse,
)
from app.service import KRSManager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SEVIMA-Mini — Modul KRS (Kartu Rencana Studi)",
    description=(
        "API Pengisian KRS dengan Chain of Responsibility Validation, "
        "State Machine, Transaction Management (ACID), Optimistic/Pessimistic Locking, "
        "dan KRS Recommendation AI."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(KRSError)
async def krs_error_handler(_request: Request, exc: KRSError) -> JSONResponse:
    """Satu exception handler polimorfis untuk KRSError dan seluruh turunannya:
    - KRSError             -> 400
    - ForbiddenError       -> 403
    - NotFoundError        -> 404
    - TransitionError      -> 409
    - KRSLockedError       -> 409
    - ValidationInputError -> 422
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


@app.get("/api/krs/{nim}", response_model=KRSResponse)
def get_krs(nim: str, db: Session = Depends(get_db)):
    return KRSManager(db).get_krs(nim)


@app.post("/api/krs/{nim}/courses", response_model=KRSResponse, status_code=201)
def add_course(nim: str, body: AddCourseRequest, db: Session = Depends(get_db)):
    return KRSManager(db).add_course(nim, body.kode_mk)


@app.delete("/api/krs/{nim}/courses/{kode_mk}", response_model=KRSResponse)
def remove_course(nim: str, kode_mk: str, db: Session = Depends(get_db)):
    return KRSManager(db).remove_course(nim, kode_mk)


@app.get("/api/krs/{nim}/validate", response_model=ValidationResponse)
def validate_krs(nim: str, db: Session = Depends(get_db)):
    failures = KRSManager(db).validate_krs(nim)
    return ValidationResponse(
        valid=(len(failures) == 0),
        errors=[f.message for f in failures],
    )


@app.post("/api/krs/{nim}/submit", response_model=KRSResponse)
def submit_krs(nim: str, db: Session = Depends(get_db)):
    return KRSManager(db).submit_krs(nim)


@app.post("/api/krs/{nim}/approve", response_model=KRSResponse)
def approve_krs(nim: str, body: ApproveKRSRequest, db: Session = Depends(get_db)):
    # Catatan limitasi: dosen_pa_id masih dikirim via body karena modul login
    # belum dibuat; idealnya diambil dari identitas/token login.
    return KRSManager(db).approve_krs(
        nim=nim,
        dosen_pa_id=body.dosen_pa_id,
        expected_version=body.version,
    )


@app.post("/api/krs/{nim}/revise", response_model=KRSResponse)
def revise_krs(nim: str, body: ReviseKRSRequest, db: Session = Depends(get_db)):
    return KRSManager(db).revise_krs(
        nim=nim,
        dosen_pa_id=body.dosen_pa_id,
        catatan=body.catatan,
        expected_version=body.version,
    )


@app.post("/api/krs/{nim}/recommend", response_model=RecommendResponse)
def recommend_krs(nim: str, body: RecommendRequest, db: Session = Depends(get_db)):
    krs = KRSManager(db).get_krs(nim)
    agent = KRSRecommendationAgent(db)
    rec = agent.recommend(
        nim=nim,
        desired_courses=body.desired_courses,
        semester=krs.semester,
        max_sks=body.max_sks,
        target_sks=body.target_sks,
    )
    return RecommendResponse(
        selected_courses=[
            MatakuliahResponse.model_validate(mk) for mk in rec.selected_courses
        ],
        total_sks=rec.total_sks,
        wajib_count=rec.wajib_count,
        pilihan_count=rec.pilihan_count,
        skipped_courses=rec.skipped_courses,
        validated=rec.validated,
        tool_trace=rec.tool_trace,
    )
