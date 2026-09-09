"""Application-lifetime SQLite checkpointer for both LangGraph workflows."""
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import get_settings


_connection: aiosqlite.Connection | None = None
_checkpointer: AsyncSqliteSaver | None = None


async def init_checkpointer() -> AsyncSqliteSaver:
    """Open the checkpoint database and create LangGraph's tables."""
    global _connection, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    db_path = Path(get_settings().CHECKPOINT_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _connection = await aiosqlite.connect(str(db_path))
    _checkpointer = AsyncSqliteSaver(_connection)
    await _checkpointer.setup()
    return _checkpointer


def get_checkpointer() -> AsyncSqliteSaver:
    """Return the initialized saver; initialization belongs to FastAPI lifespan."""
    if _checkpointer is None:
        raise RuntimeError("SQLite checkpointer has not been initialized")
    return _checkpointer


async def delete_checkpoint(thread_id: str) -> None:
    """删除一个 LangGraph 线程的全部 checkpoint 状态。"""
    await get_checkpointer().adelete_thread(thread_id)


async def close_checkpointer() -> None:
    """Flush and close the application-owned SQLite connection."""
    global _connection, _checkpointer
    if _connection is not None:
        await _connection.close()
    _connection = None
    _checkpointer = None
