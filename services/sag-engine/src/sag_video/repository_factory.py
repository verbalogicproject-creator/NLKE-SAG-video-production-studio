from __future__ import annotations

from pathlib import Path

from .store import Store


def create_repository(
    *,
    backend: str,
    database_path: str | Path,
    database_url: str = "",
    seed: bool = False,
):
    if backend == "sqlite":
        return Store(database_path)
    if backend == "postgres":
        if not database_url:
            raise RuntimeError("DATABASE_URL is required when SAG_REPOSITORY_BACKEND=postgres")
        from .postgres_store import PostgreSQLStore

        return PostgreSQLStore(database_url, seed=seed)
    raise RuntimeError(f"unsupported SAG repository backend: {backend}")
