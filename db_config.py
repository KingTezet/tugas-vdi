"""Konfigurasi koneksi database dari environment variables (.env).

Tidak ada credential yang di-hardcode: semua dibaca dari .env (lokal)
atau dari Secrets / Environment Variables platform deploy.
"""
import os
from urllib.parse import quote_plus

import redis
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable '{name}' belum diset. "
            "Salin .env.example menjadi .env lalu isi nilainya."
        )
    return value


def get_postgres_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        # Neon/Supabase/Heroku sering memberi prefix 'postgres://'
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    user = quote_plus(_require("POSTGRES_USER"))
    password = quote_plus(_require("POSTGRES_PASSWORD"))
    host = _require("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = _require("POSTGRES_DB")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def get_pg_engine() -> Engine:
    return create_engine(get_postgres_url(), pool_pre_ping=True)


def get_redis_client() -> redis.Redis:
    url = os.getenv("REDIS_URL")
    if url:
        return redis.from_url(url, decode_responses=True)
    return redis.Redis(
        host=_require("REDIS_HOST"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD") or None,
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=True,
    )


# Nama key Redis Stream yang menampung log aktivitas
REDIS_STREAM_KEY = "activity_log"
