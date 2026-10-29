"""PostgreSQL-backed cache for slow external lookups (flights, weather, hotels)."""

import json
from typing import Any

from psycopg_pool import ConnectionPool


class PostgresCache:
    """A tiny key/value cache with expiry, stored in one table.

    Values must be JSON serialisable. A tuple comes back as a list.
    """

    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        with pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_cache (
                    key        text PRIMARY KEY,
                    value      jsonb NOT NULL,
                    expires_at timestamptz NOT NULL
                )
                """
            )

    def get(self, key: str) -> Any | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT value FROM tool_cache WHERE key = %s AND expires_at > now()",
                (key,),
            ).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO tool_cache (key, value, expires_at)
                VALUES (%s, %s::jsonb, now() + make_interval(secs => %s))
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at
                """,
                (key, json.dumps(value), ttl_seconds),
            )
