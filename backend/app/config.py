# CareerMind AI Configuration
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "CareerMind AI"
    APP_VERSION: str = "1.0.0"
    APP_DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./careermind.db"
    CHECKPOINT_DB_PATH: str = "./data/langgraph_checkpoints.db"

    # JWT
    JWT_SECRET_KEY: str = "careermind-dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # LLM Configuration
    LLM_PROVIDER: str = "dashscope"  # 当前仅支持 DashScope（OpenAI 兼容协议）
    # 千问 / 阿里云百炼 DashScope（OpenAI 兼容接口）
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_MODEL: str = "qwen-plus"
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_TEMPERATURE: float = 0.3
    LLM_ENABLE_THINKING: bool = False
    # Per-attempt transport timeout and total operation timeout including retries.
    LLM_TIMEOUT_SECONDS: float = 120.0
    LLM_OPERATION_TIMEOUT_SECONDS: float = 250.0
    LLM_MAX_RETRIES: int = 1

    # Embedding（千问：text-embedding-v3 / text-embedding-v4）
    EMBEDDING_MODEL: str = "text-embedding-v3"
    # 单次 Embedding 请求的文本数量；DashScope v3 上限为 10。
    EMBEDDING_BATCH_SIZE: int = 10
    EMBEDDING_TIMEOUT_SECONDS: float = 45.0
    EMBEDDING_MAX_RETRIES: int = 1

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 10
    UPLOAD_DIR: str = "./uploads"

    # CORS
    CORS_ORIGINS: list = [
        "http://localhost:5173", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://127.0.0.1:3000",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ]

    # Vector Store
    CHROMA_PERSIST_DIR: str = "./chroma_db"

    # 数据源 API（RAG 采集）
    JSEARCH_API_KEY: str = ""                      # RapidAPI JSearch key
    JSEARCH_RAPIDAPI_HOST: str = "jsearch.p.rapidapi.com"
    JSEARCH_MAX_RESULTS: int = 20                  # 单次采集最大岗位数
    TAVILY_API_KEY: str = ""
    JSEARCH_TIMEOUT_SECONDS: float = 30.0
    TAVILY_TIMEOUT_SECONDS: float = 30.0
    EXTERNAL_API_MAX_RETRIES: int = 1
    EXTERNAL_API_RETRY_BACKOFF_SECONDS: float = 1.0
    TAVILY_MAX_RESULTS: int = 10                   # 单次采集最大网页数
    LEARNING_RESOURCE_CONCURRENCY: int = Field(default=3, ge=1, le=3)
    INTERVIEW_RAG_MIN_SCORE: float = 0.5          # 面试题与目标岗位的最低余弦相似度

    # 知识中心 Hybrid Search + 本地 BGE Rerank
    HYBRID_CANDIDATE_LIMIT: int = 50
    HYBRID_RRF_K: int = 60
    RERANK_FINAL_LIMIT: int = 20
    BGE_RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    BGE_RERANK_MODEL_DIR: str = "./venv/models/bge-reranker-v2-m3"
    BGE_RERANK_DEVICE: str = "auto"
    BGE_RERANK_BATCH_SIZE: int = 8
    BGE_RERANK_MAX_LENGTH: int = 512
    BGE_RERANK_TIMEOUT_SECONDS: float = 20.0

    # Single-machine demo: readable console logging.
    LOG_LEVEL: str = "INFO"

    # Agent
    AGENT_RECURSION_LIMIT: int = 25

    model_config = {"env_file": ".env", "extra": "allow"}

@lru_cache()
def get_settings() -> Settings:
    return Settings()
