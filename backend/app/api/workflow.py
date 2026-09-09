# CareerMind AI Workflow API
"""
Two independent paths:

  POST /api/v1/workflow/career-planning   → 路径A: 规划提升
  POST /api/v1/interview/start            → 路径B: 模拟面试 (in interview.py)
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.workflow import (
    CareerPlanningRequest,
    WorkflowStatusResponse,
    CareerPlanningResultResponse,
    CareerPlanningHistoryResponse,
)
from app.services.workflow_service import WorkflowService
from app.utils.security import get_current_user_id

router = APIRouter(prefix="/api/v1/workflow", tags=["Workflow"])


# ============================================================
# Path A: 规划提升
# ============================================================

@router.post("/career-planning", response_model=WorkflowStatusResponse, status_code=201)
async def start_career_planning(
    data: CareerPlanningRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """路径A — 规划提升。

    简历分析与目标岗位搜索并行 → 技能差距分析 → 生成学习规划。

    target_position 必填；简历可传 resume_id（已上传解析）或 resume_text（纯文本）。
    返回 run_id，用于轮询状态和获取结果。
    """
    return await WorkflowService.start_career_planning(db, user_id, data)


@router.get("/plans", response_model=CareerPlanningHistoryResponse)
async def list_career_plans(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的历史职业规划方案（路径A：规划提升）。"""
    return await WorkflowService.list_plans(db, user_id)

@router.delete("/plans/{run_id}", status_code=204)
async def delete_career_plan(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除一条职业规划历史记录。"""
    await WorkflowService.delete_plan(db, user_id, run_id)
    return Response(status_code=204)


@router.get("/{run_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询工作流执行状态（路径A 通用）。"""
    return await WorkflowService.get_status(db, user_id, run_id)


@router.post("/{run_id}/resume", response_model=WorkflowStatusResponse)
async def resume_career_planning(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """用户显式恢复一条因后端重启而中断的路径 A 任务。"""
    return await WorkflowService.resume_career_planning(db, user_id, run_id)


@router.get("/{run_id}/result", response_model=CareerPlanningResultResponse)
async def get_career_planning_result(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取规划提升的完整结果。"""
    return await WorkflowService.get_career_planning_result(db, user_id, run_id)
