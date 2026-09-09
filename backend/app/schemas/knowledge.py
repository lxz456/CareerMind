# CareerMind AI Knowledge Schemas
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Union, Literal
from datetime import datetime


# ---- 面试题 ----
class QuestionItem(BaseModel):
    id: str
    question: str
    category: Optional[str] = None
    difficulty: Optional[str] = None
    topic: Optional[str] = None
    expected_points: List[str] = Field(default_factory=list)
    score: Optional[float] = None       # Rerank 相关性；降级时为融合分，范围 0-1
    created_at: Optional[datetime] = None


# ---- 学习资源 ----
class ResourceItem(BaseModel):
    id: str
    name: str
    type: Optional[str] = None
    url: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    score: Optional[float] = None
    created_at: Optional[datetime] = None


class KnowledgeSearchRequest(BaseModel):
    type: Literal["interview", "resource"] = Field(..., description="interview | resource")
    query: str = Field(..., min_length=1, description="查询问题")
    category: Optional[str] = Field(None, description="面试题分类 / 资源类型过滤")
    difficulty: Optional[Literal["easy", "medium", "hard"]] = Field(None, description="难度过滤（仅面试题）")
    limit: int = Field(default=10, ge=1, le=20)
    refresh: bool = Field(
        False,
        description="True 时生成新面试题，或通过 Tavily 采集新学习资源并入库",
    )

    model_config = {"extra": "forbid"}

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("查询内容不能为空")
        return value


class KnowledgeSearchResponse(BaseModel):
    type: str
    results: List[Union[QuestionItem, ResourceItem]] = Field(default_factory=list)
    from_cache: bool = False
