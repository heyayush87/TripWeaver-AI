"""PostgreSQL connection pool and LangGraph checkpointer."""

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from tripweaver.cache_store import PostgresCache
from tripweaver.config import get_database_url
from tripweaver.utils import enable_shared_cache


DATABASE_URL = get_database_url()


_pool = ConnectionPool(
    conninfo=DATABASE_URL,
    max_size=10,
    kwargs={"autocommit": True, "row_factory": dict_row},
    check=ConnectionPool.check_connection,
    open=True,
)

checkpointer = PostgresSaver(_pool)
checkpointer.setup()

# Cache slow lookups in Postgres so they survive restarts and are shared.
enable_shared_cache(PostgresCache(_pool))
