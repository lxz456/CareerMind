# CareerMind AI Database Configuration
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from app.config import get_settings

settings = get_settings()

# One-time compatibility cleanup for databases created by older versions.
# New databases never create these columns because they are absent from ORM models.
_SQLITE_DEPRECATED_COLUMNS = {
    "users": ("skills",),
    "workflow_runs": ("interview_result",),
    "messages": ("token_count",),
    "interview_questions": ("answer_reference", "source_url"),
    "learning_resources": ("source_url",),
}

_SQLITE_REQUIRED_COLUMNS = {
    "workflow_runs": {"error_code": "VARCHAR(50)"},
}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    # sqlite：busy_timeout=30s，避免多请求并发写时立刻抛 "database is locked"
    connect_args=(
        {"check_same_thread": False, "timeout": 30}
        if "sqlite" in settings.DATABASE_URL else {}
    ),
)

if "sqlite" in settings.DATABASE_URL:
    # busy_timeout 是 per-connection 设置，必须对每条新连接都执行；
    # 否则多请求并发写库时立即抛 "database is locked"
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    """Dependency injection for database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Create all tables on startup."""
    # 确保所有 ORM model 已注册到 Base.metadata，不能依赖路由的偶然导入顺序。
    __import__("app.models")

    async with engine.begin() as conn:
        if "sqlite" in settings.DATABASE_URL:
            # WAL 模式：读写可并发，显著降低 "database is locked"
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA busy_timeout=30000")
            await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in settings.DATABASE_URL:
            await _add_missing_sqlite_columns(conn)
            await _drop_deprecated_sqlite_columns(conn)
            await _init_knowledge_fts(conn)


async def _add_missing_sqlite_columns(conn) -> None:
    """Apply tiny additive migrations needed by this SQLite demo."""
    for table, required_columns in _SQLITE_REQUIRED_COLUMNS.items():
        result = await conn.exec_driver_sql(f'PRAGMA table_info("{table}")')
        existing_columns = {row[1] for row in result.fetchall()}
        for column, sql_type in required_columns.items():
            if column not in existing_columns:
                await conn.exec_driver_sql(
                    f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'
                )


async def _drop_deprecated_sqlite_columns(conn) -> None:
    """Remove legacy, unused columns that SQLAlchemy create_all cannot migrate."""
    for table, deprecated_columns in _SQLITE_DEPRECATED_COLUMNS.items():
        result = await conn.exec_driver_sql(f'PRAGMA table_info("{table}")')
        existing_columns = {row[1] for row in result.fetchall()}
        for column in deprecated_columns:
            if column in existing_columns:
                await conn.exec_driver_sql(
                    f'ALTER TABLE "{table}" DROP COLUMN "{column}"'
                )


async def _init_knowledge_fts(conn) -> None:
    """创建并回填知识中心 FTS5 索引，用触发器与业务表保持同步。"""
    statements = (
        """CREATE VIRTUAL TABLE IF NOT EXISTS interview_questions_fts USING fts5(
            id UNINDEXED, question, topic, category UNINDEXED,
            difficulty UNINDEXED, tokenize='trigram'
        )""",
        """CREATE VIRTUAL TABLE IF NOT EXISTS learning_resources_fts USING fts5(
            id UNINDEXED, name, topic, description, type UNINDEXED,
            url UNINDEXED, tokenize='trigram'
        )""",
        """CREATE TRIGGER IF NOT EXISTS interview_questions_fts_ai
        AFTER INSERT ON interview_questions BEGIN
            INSERT INTO interview_questions_fts(id, question, topic, category, difficulty)
            VALUES (new.id, new.question, coalesce(new.topic, ''),
                    coalesce(new.category, ''), coalesce(new.difficulty, ''));
        END""",
        """CREATE TRIGGER IF NOT EXISTS interview_questions_fts_ad
        AFTER DELETE ON interview_questions BEGIN
            DELETE FROM interview_questions_fts WHERE id = old.id;
        END""",
        """CREATE TRIGGER IF NOT EXISTS interview_questions_fts_au
        AFTER UPDATE ON interview_questions BEGIN
            DELETE FROM interview_questions_fts WHERE id = old.id;
            INSERT INTO interview_questions_fts(id, question, topic, category, difficulty)
            VALUES (new.id, new.question, coalesce(new.topic, ''),
                    coalesce(new.category, ''), coalesce(new.difficulty, ''));
        END""",
        """CREATE TRIGGER IF NOT EXISTS learning_resources_fts_ai
        AFTER INSERT ON learning_resources BEGIN
            INSERT INTO learning_resources_fts(id, name, topic, description, type, url)
            VALUES (new.id, new.name, coalesce(new.topic, ''),
                    coalesce(new.description, ''), coalesce(new.type, ''),
                    coalesce(new.url, ''));
        END""",
        """CREATE TRIGGER IF NOT EXISTS learning_resources_fts_ad
        AFTER DELETE ON learning_resources BEGIN
            DELETE FROM learning_resources_fts WHERE id = old.id;
        END""",
        """CREATE TRIGGER IF NOT EXISTS learning_resources_fts_au
        AFTER UPDATE ON learning_resources BEGIN
            DELETE FROM learning_resources_fts WHERE id = old.id;
            INSERT INTO learning_resources_fts(id, name, topic, description, type, url)
            VALUES (new.id, new.name, coalesce(new.topic, ''),
                    coalesce(new.description, ''), coalesce(new.type, ''),
                    coalesce(new.url, ''));
        END""",
        """INSERT INTO interview_questions_fts(id, question, topic, category, difficulty)
        SELECT q.id, q.question, coalesce(q.topic, ''), coalesce(q.category, ''),
               coalesce(q.difficulty, '')
        FROM interview_questions AS q
        WHERE NOT EXISTS (
            SELECT 1 FROM interview_questions_fts AS f WHERE f.id = q.id
        )""",
        """INSERT INTO learning_resources_fts(id, name, topic, description, type, url)
        SELECT r.id, r.name, coalesce(r.topic, ''), coalesce(r.description, ''),
               coalesce(r.type, ''), coalesce(r.url, '')
        FROM learning_resources AS r
        WHERE NOT EXISTS (
            SELECT 1 FROM learning_resources_fts AS f WHERE f.id = r.id
        )""",
    )
    for statement in statements:
        await conn.exec_driver_sql(statement)
