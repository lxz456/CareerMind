# CareerMind AI — Repository 层（数据访问层 / DAL）
#
# 分层依赖（单向）：
#   api → service → repository → SQLAlchemy models / VectorStore
#
# 职责边界：
#   - repository 只做数据访问，屏蔽 SQLAlchemy 和 ChromaDB 的具体调用。
#   - 不包含业务规则、不抛 HTTPException（那是 service 的职责）。
#   - 跨表编排、LLM/外部 API 调用、错误判断 → 全部留在 service。
#   - transaction/commit 边界由 service 持有；repository 可按需 flush 以取得主键或同步 ORM 状态。
#
# 这样 service 看不到 select(...)/db.add(...)、集合名或 Chroma where 等存储细节。

from app.repositories.user_repo import UserRepo
from app.repositories.resume_repo import ResumeRepo
from app.repositories.conversation_repo import ConversationRepo
from app.repositories.workflow_repo import WorkflowRepo
from app.repositories.knowledge_repo import KnowledgeRepo
from app.repositories.vector_knowledge_repo import VectorKnowledgeRepo

__all__ = [
    "UserRepo",
    "ResumeRepo",
    "ConversationRepo",
    "WorkflowRepo",
    "KnowledgeRepo",
    "VectorKnowledgeRepo",
]
