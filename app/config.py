import os

class Settings:
    PROJECT_NAME: str = "Sistem Penerimaan Mahasiswa Baru (PMB)"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/pmb"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./pmb.db")

settings = Settings()
