import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def storage_path():
    return (ROOT / os.getenv("FABRITAKE_STORAGE", "storage")).resolve()


def origins():
    return [item.strip() for item in os.getenv(
        "FABRITAKE_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",") if item.strip()]
