import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.models.program_studi import ProgramStudi
from app.models.jalur_masuk import JalurMasuk
from app.routers.pmb import router as pmb_router

def seed_initial_data():
    """Seed initial program studi and jalur masuk data if not already present."""
    db = SessionLocal()
    try:
        # Seed Program Studi
        if db.query(ProgramStudi).count() == 0:
            default_prodi = [
                ProgramStudi(kode="001", nama="Teknik Informatika", fakultas="Fakultas Ilmu Komputer"),
                ProgramStudi(kode="002", nama="Sistem Informasi", fakultas="Fakultas Ilmu Komputer"),
                ProgramStudi(kode="003", nama="Teknik Komputer", fakultas="Fakultas Teknik"),
            ]
            db.add_all(default_prodi)
            db.commit()

        # Seed Jalur Masuk
        if db.query(JalurMasuk).count() == 0:
            default_jalur = [
                JalurMasuk(kode="SNBP", nama="Seleksi Nasional Berdasarkan Prestasi", keterangan="Jalur prestasi rapor siswa"),
                JalurMasuk(kode="SNBT", nama="Seleksi Nasional Berdasarkan Tes", keterangan="Jalur tes UTBK nasional"),
                JalurMasuk(kode="Mandiri", nama="Seleksi Mandiri Kampus", keterangan="Jalur mandiri reguler & kemitraan"),
            ]
            db.add_all(default_jalur)
            db.commit()
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_initial_data()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="REST API Sistem Penerimaan Mahasiswa Baru (PMB) dengan Generator NIM Otomatis",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for frontend/browser support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom validation error handler: returns 400 Bad Request instead of 422
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = []
    formatted_errors = []
    for err in exc.errors():
        loc_str = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Validation error")
        error_details.append(f"{loc_str}: {msg}")
        formatted_errors.append({
            "loc": [str(l) for l in err.get("loc", [])],
            "msg": str(msg),
            "type": str(err.get("type", ""))
        })
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": "; ".join(error_details),
            "errors": formatted_errors
        }
    )

# Include routers: both with prefix /api/pmb and without prefix for flexible endpoints
app.include_router(pmb_router, prefix=settings.API_PREFIX)
app.include_router(pmb_router, prefix="")

# Serve web UI form at root
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/", include_in_schema=False)
def serve_home():
    index_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Selamat datang di API Penerimaan Mahasiswa Baru (PMB). Buka /docs untuk Swagger UI."}
