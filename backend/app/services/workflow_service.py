"""路径 A（职业规划）的业务编排服务。

本模块位于 API 与 LangGraph/Repository 之间，负责：创建工作流业务记录、
把耗时的图执行放入后台、将节点进度和最终结果写回数据库、管理中断与显式恢复，
以及为 API 提供状态、结果、历史列表和删除能力。路径 B 由 interview_service.py 管理。
"""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.repositories import WorkflowRepo, ResumeRepo
from app.agents.graph import get_checkpoint_state, run_career_planning_pipeline
from app.database import async_session
from app.memory.checkpoint import delete_checkpoint
from app.services.knowledge_ingestion_service import KnowledgeIngestionService
from app.services.resume_service import calculate_resume_score
from app.schemas.workflow import (
    CareerPlanningRequest,
    WorkflowStatusResponse,
    CareerPlanningResultResponse,
    CareerPlanningHistoryResponse,
    CareerPlanningHistoryItem,
)


STEP_PROGRESS = {
    "parallel_analysis": 0,
    "resume_analysis": 20,
    "job_search": 20,
    "skill_gap": 60,
    "career_plan": 85,
    "summary": 100,
}
# 按 run_id 保存当前 Python 进程内仍在运行的路径 A 后台任务。
# 除了防止任务对象被提前回收，也用于阻止同一规划被重复调度。
_pipeline_tasks: dict[str, asyncio.Task] = {}
logger = logging.getLogger(__name__)


def _workflow_error_code(error: Exception | str) -> str:
    """Map technical failures to a small, stable set of frontend-safe codes."""
    message = str(error).casefold()
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)) or "timed out" in message or "timeout" in message:
        return "LLM_TIMEOUT"
    if "checkpoint" in message:
        return "CHECKPOINT_MISSING"
    if "no matching jobs" in message:
        return "JSEARCH_NO_RESULTS"
    if "jsearch" in message or "job search" in message:
        return "JSEARCH_FAILED"
    if "职位要求" in message or "job requirements" in message:
        return "JOB_REQUIREMENTS_MISSING"
    if "json" in message or "decode" in message:
        return "LLM_INVALID_OUTPUT"
    if "connection" in message or "disconnected" in message:
        return "EXTERNAL_SERVICE_CONNECTION_ERROR"
    return "WORKFLOW_FAILED"


def _workflow_error_message(error_code: str, current_step: str | None) -> str:
    """Return a short Chinese message safe to persist and show in the UI."""
    messages = {
        "LLM_TIMEOUT": "模型处理超时，请稍后继续或重新尝试",
        "CHECKPOINT_MISSING": "无法恢复任务：未找到断点或原始简历",
        "JSEARCH_NO_RESULTS": "没有找到匹配的真实岗位，请调整目标职位或筛选条件",
        "JSEARCH_FAILED": "岗位搜索服务暂时不可用，请稍后重试",
        "JOB_REQUIREMENTS_MISSING": "岗位信息中缺少可用于技能分析的职位要求",
        "LLM_INVALID_OUTPUT": "模型返回格式异常，请重新尝试",
        "EXTERNAL_SERVICE_CONNECTION_ERROR": "外部服务连接失败，请稍后重试",
    }
    if error_code in messages:
        return messages[error_code]
    step_labels = {
        "parallel_analysis": "简历与岗位分析",
        "resume_analysis": "简历分析",
        "job_search": "岗位搜索",
        "skill_gap": "技能差距分析",
        "career_plan": "职业规划生成",
        "summary": "结果汇总",
    }
    return f"{step_labels.get(current_step, '职业规划')}失败，请查看后端日志后重试"


def _track_pipeline(run_id: str, coroutine) -> tuple[asyncio.Task, bool]:
    """创建并登记一个路径 A 后台任务。

    如果同一 run_id 已有未结束任务，则关闭新建的协程并返回现有任务，避免重复执行。
    返回值第二项表示本次是否真的创建了新任务。
    """
    existing = _pipeline_tasks.get(run_id)
    if existing and not existing.done():
        coroutine.close()
        return existing, False

    task = asyncio.create_task(coroutine)
    _pipeline_tasks[run_id] = task

    def forget_pipeline(done_task: asyncio.Task) -> None:
        if _pipeline_tasks.get(run_id) is done_task:
            _pipeline_tasks.pop(run_id, None)

    task.add_done_callback(forget_pipeline)
    return task, True


class WorkflowService:

    # ============================================================
    # Path A: 规划提升
    # ============================================================

    @staticmethod
    async def start_career_planning(
        db: AsyncSession,
        user_id: str,
        data: CareerPlanningRequest,
    ) -> WorkflowStatusResponse:
        """创建路径 A 任务并立即返回初始状态。

        先从请求正文或已有简历记录取得原文，然后创建 `workflow_runs` 记录并生成
        独立的 LangGraph `thread_id`。业务记录提交成功后才调度后台流水线，避免后台
        session 查询不到尚未提交的 run。该方法不等待 LLM 执行完成。

        图流程：`(resume_analysis || job_search) → skill_gap → career_plan → summary`。
        """
        # 1. 解析输入：直接文本优先，否则按当前用户和 resume_id 读取已上传简历。
        resume_text = data.resume_text or ""
        if not resume_text and data.resume_id:
            resume = await ResumeRepo.get_by_id_and_user(db, data.resume_id, user_id)
            if resume and resume.raw_text:
                resume_text = resume.raw_text
                resume.status = "processing"
                resume.analysis_summary = None
            else:
                raise HTTPException(status_code=400, detail="Resume not found or text extraction failed")

        if not resume_text:
            raise HTTPException(
                status_code=400,
                detail="Either resume_id or resume_text is required",
            )

        # 2. 创建可被前端轮询、也可在进程重启后恢复的持久化任务记录。
        run = await WorkflowRepo.create(
            db,
            user_id=user_id,
            workflow_type="career_planning",
            status="running",
            current_step="parallel_analysis",
            completed_steps=[],
            input_data={
                "target_position": data.target_position,
                "job_requirements": data.job_requirements,
                "target_location": data.target_location,
                "resume_id": data.resume_id,
                # Direct-text requests need their original input if the process
                # stops before LangGraph writes its first checkpoint.
                "resume_text": resume_text if not data.resume_id else None,
            },
            progress=0.0,
        )
        thread_id = f"career_planning:{run.id}"
        run.thread_id = thread_id
        # Persist the run and thread id atomically before scheduling background work.
        await db.commit()

        # 3. 把 LLM 流水线丢到后台执行，接口立即返回 run_id。
        # 否则同步等整条流水线跑完会远超前端超时（此前报 timeout 120000ms）。
        _track_pipeline(
            run.id,
            WorkflowService._run_pipeline(
                user_id=user_id,
                resume_text=resume_text,
                target_position=data.target_position,
                job_requirements=data.job_requirements or "",
                target_location=data.target_location or "",
                resume_id=data.resume_id or "",
                thread_id=thread_id,
                run_id=run.id,
                resume_from_checkpoint=False,
            )
        )

        return WorkflowStatusResponse(
            run_id=run.id,
            path="career_planning",
            status="running",
            current_step="parallel_analysis",
            completed_steps=[],
            progress=0.0,
            error_message=None,
            error_code=None,
            created_at=run.created_at,
            completed_at=None,
        )

    @staticmethod
    async def _run_pipeline(
        user_id: str,
        resume_text: str,
        target_position: str,
        resume_id: str,
        thread_id: str,
        run_id: str,
        job_requirements: str = "",
        target_location: str = "",
        resume_from_checkpoint: bool = False,
    ) -> None:
        """在独立数据库 session 中执行或恢复路径 A。

        `resume_from_checkpoint=False` 时从初始状态运行；为 True 时给 LangGraph 传入
        空输入，使其从相同 `thread_id` 的最新 checkpoint 继续。图正常结束后，把各节点
        结果写入 `workflow_runs`，并根据 `error_message` 标记 completed 或 failed。

        如果图本身抛出未捕获异常，会尽量从 checkpoint 取回已经成功的简历分析结果，
        避免 Resume 长期停留在 processing。无论成功或失败，最终都会提交本次 session。
        """
        async with async_session() as session:
            logger.info(
                "Career planning started run_id=%s thread_id=%s resumed=%s",
                run_id, thread_id, resume_from_checkpoint,
            )
            try:
                # Graph 层负责状态流转；on_step 回调负责把中间进度暴露给前端轮询。
                result = await run_career_planning_pipeline(
                    user_id=user_id,
                    resume_text=resume_text,
                    target_position=target_position,
                    job_requirements=job_requirements,
                    target_location=target_location,
                    resume_id=resume_id,
                    thread_id=thread_id,
                    resume_from_checkpoint=resume_from_checkpoint,
                    on_step=WorkflowService._make_progress_writer(run_id),
                )
                now = datetime.now(timezone.utc)
                run = await WorkflowRepo.get_by_id(session, run_id)
                await WorkflowService._persist_resume_analysis(
                    session, user_id, resume_id, result
                )
                await KnowledgeIngestionService.ingest_resources(
                    session, result.get("knowledge_resources") or []
                )
                if run:
                    # 将 LangGraph 最终状态拆分到业务表的各结果字段中，供历史接口直接读取。
                    run.resume_result = result.get("resume_data")
                    run.job_result = {"jobs": result.get("job_results")} if result.get("job_results") else None
                    run.skill_gap_result = result.get("skill_gap_data")
                    run.career_plan_result = result.get("career_plan_data")
                    run.summary = result.get("final_summary")
                    run.completed_steps = result.get("completed_steps", [])
                    if result.get("error_message"):
                        run.status = "failed"
                        technical_error = result["error_message"]
                        run.error_code = _workflow_error_code(technical_error)
                        run.error_message = _workflow_error_message(
                            run.error_code, run.current_step
                        )
                        logger.error(
                            "Career planning failed run_id=%s step=%s error_code=%s error=%s",
                            run_id, run.current_step, run.error_code, technical_error,
                        )
                    else:
                        run.current_step = "summary"
                        run.status = "completed"
                        run.progress = 100.0
                        run.error_code = None
                        run.error_message = None
                        logger.info("Career planning completed run_id=%s", run_id)
                    run.completed_at = now
            except Exception as e:
                logger.exception("Career planning crashed run_id=%s thread_id=%s", run_id, thread_id)
                # 后续节点异常时，checkpoint 中可能已有成功的简历分析，需要单独保留下来。
                try:
                    checkpoint = await get_checkpoint_state(thread_id)
                    if checkpoint:
                        await WorkflowService._persist_resume_analysis(
                            session, user_id, resume_id, checkpoint
                        )
                except Exception:
                    pass
                run = await WorkflowRepo.get_by_id(session, run_id)
                if run:
                    run.status = "failed"
                    run.error_code = _workflow_error_code(e)
                    run.error_message = _workflow_error_message(
                        run.error_code, run.current_step
                    )
            finally:
                await session.commit()

    @staticmethod
    async def _persist_resume_analysis(
        session: AsyncSession,
        user_id: str,
        resume_id: str,
        graph_state: dict,
    ) -> None:
        """把 Graph 中的简历分析结果同步回 Resume 业务记录。

        使用直接传入 `resume_text` 的任务没有 resume_id，因此直接返回。分析成功时保存
        结构化数据、完整度评分和总结；简历节点失败时保存失败状态及原因。本函数只修改
        ORM 对象，不自行 commit，由外层 `_run_pipeline()` 统一提交事务。
        """
        if not resume_id:
            return
        resume = await ResumeRepo.get_by_id_and_user(session, resume_id, user_id)
        if not resume:
            return

        parsed_data = graph_state.get("resume_data")
        if parsed_data:
            resume.parsed_data = parsed_data
            resume.analysis_score = calculate_resume_score(parsed_data)
            resume.analysis_summary = parsed_data.get("overall_assessment", "")
            resume.status = "completed"
        elif graph_state.get("resume_error"):
            resume.status = "failed"
            resume.analysis_summary = graph_state["resume_error"]

    @staticmethod
    async def mark_interrupted_workflows() -> int:
        """应用启动时把上一个进程遗留的 running 路径 A 任务标记为 interrupted。

        服务启动本身不恢复任务。用户之后可在个人中心点击“继续”，由恢复接口检查
        checkpoint/原始简历并重新调度。返回本次被标记的任务数。
        """
        async with async_session() as session:
            runs = await WorkflowRepo.list_running_career_plans(session)
            for run in runs:
                run.status = "interrupted"
                run.error_code = None
                run.error_message = None
                run.completed_at = None
            await session.commit()
        return len(runs)

    @staticmethod
    async def resume_career_planning(
        db: AsyncSession,
        user_id: str,
        run_id: str,
    ) -> WorkflowStatusResponse:
        """由用户显式恢复一条中断的路径 A 任务。

        有 checkpoint 时从最近状态继续；首个 checkpoint 尚未产生时，使用保存的
        resume_text 或 Resume 记录从头执行。同一进程内对相同 run_id 重复调用是幂等的。
        """
        run = await WorkflowRepo.get_plan_by_id_and_user(db, run_id, user_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        if run.status in {"completed", "failed"}:
            raise HTTPException(
                status_code=409,
                detail=f"Workflow cannot be resumed (status: {run.status})",
            )
        if run.status not in {"pending", "running", "interrupted"}:
            raise HTTPException(
                status_code=409,
                detail=f"Workflow cannot be resumed (status: {run.status})",
            )

        existing = _pipeline_tasks.get(run.id)
        if existing and not existing.done():
            return await WorkflowService.get_status(db, user_id, run.id)

        input_data = run.input_data or {}
        thread_id = run.thread_id or f"career_planning:{run.id}"
        checkpoint = await get_checkpoint_state(thread_id)
        resume_text = input_data.get("resume_text") or ""
        resume_id = input_data.get("resume_id") or ""
        if not checkpoint and resume_id:
            resume = await ResumeRepo.get_by_id_and_user(db, resume_id, user_id)
            resume_text = resume.raw_text if resume and resume.raw_text else ""

        if not checkpoint and not resume_text:
            raise HTTPException(
                status_code=409,
                detail="无法恢复：未找到 checkpoint 或原始简历",
            )

        run.thread_id = thread_id
        run.status = "running"
        run.error_code = None
        run.error_message = None
        run.completed_at = None
        await db.commit()

        _, created = _track_pipeline(
            run.id,
            WorkflowService._run_pipeline(
                user_id=run.user_id,
                resume_text=resume_text,
                target_position=input_data.get("target_position") or "",
                job_requirements=input_data.get("job_requirements") or "",
                target_location=input_data.get("target_location") or "",
                resume_id=resume_id,
                thread_id=thread_id,
                run_id=run.id,
                resume_from_checkpoint=bool(checkpoint),
            ),
        )
        logger.info(
            "Career planning resume requested run_id=%s checkpoint=%s scheduled=%s",
            run.id, bool(checkpoint), created,
        )
        return await WorkflowService.get_status(db, user_id, run.id)

    @staticmethod
    async def stop_background_workflows() -> None:
        """应用关闭前取消并等待本进程中的全部路径 A 后台任务。

        必须在关闭共享 SQLite checkpointer 之前执行，否则仍在运行的 Graph 可能继续访问
        已关闭连接。`return_exceptions=True` 用来收集取消异常，避免影响 shutdown 流程。
        """
        tasks = list(_pipeline_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _make_progress_writer(run_id: str):
        """为指定 run 创建节点进度回写回调。

        LangGraph 每产出一次合并状态就调用返回的 `write_progress()`。回调使用独立 session
        立即提交 `current_step`、`progress` 和 `completed_steps`，因此前端轮询无需等待主
        pipeline 结束。进度写入属于辅助能力，失败时回滚但不会中断核心 LLM 流程。
        """
        async def write_progress(current_step: str, progress: float, completed_steps: list) -> None:
            """将一次节点进度快照立即写入 workflow_runs。"""
            async with async_session() as s:
                try:
                    run = await WorkflowRepo.get_by_id(s, run_id)
                    if run:
                        run.current_step = current_step
                        run.progress = progress
                        run.completed_steps = completed_steps
                        await s.commit()
                        logger.info(
                            "Career planning progress run_id=%s step=%s progress=%.1f",
                            run_id, current_step, progress,
                        )
                except Exception:
                    # 进度回写失败不阻断主流程
                    await s.rollback()
                    logger.exception(
                        "Career planning progress persistence failed run_id=%s step=%s",
                        run_id, current_step,
                    )
        return write_progress

    # ============================================================
    # Shared: status / result queries
    # ============================================================

    @staticmethod
    async def get_status(
        db: AsyncSession,
        user_id: str,
        run_id: str,
    ) -> WorkflowStatusResponse:
        """查询当前用户的一条工作流状态，供前端轮询进度。

        通过 `run_id + user_id` 同时校验记录存在性与所有权；不存在时返回 404。
        此接口只返回状态、步骤、进度和错误，不返回体积较大的节点结果。
        """
        run = await WorkflowRepo.get_by_id_and_user(db, run_id, user_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        return WorkflowStatusResponse(
            run_id=run.id,
            path=run.workflow_type,
            status=run.status,
            current_step=run.current_step,
            completed_steps=run.completed_steps or [],
            progress=run.progress,
            error_message=run.error_message,
            error_code=run.error_code,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    @staticmethod
    async def get_career_planning_result(
        db: AsyncSession,
        user_id: str,
        run_id: str,
    ) -> CareerPlanningResultResponse:
        """返回一条已完成路径 A 的全部分析结果。

        失败任务会携带原始错误返回 400；仍在执行的任务同样返回 400，要求调用方继续
        查询状态。只有 completed 任务才组装简历、岗位、差距、规划和总结数据。
        """
        run = await WorkflowRepo.get_by_id_and_user(db, run_id, user_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        if run.status == "failed":
            raise HTTPException(
                status_code=400,
                detail=f"Workflow failed: {run.error_message}",
            )
        if run.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Workflow not yet completed (status: {run.status})",
            )

        return CareerPlanningResultResponse(
            run_id=run.id,
            status=run.status,
            resume_result=run.resume_result,
            job_result=run.job_result,
            skill_gap_result=run.skill_gap_result,
            career_plan_result=run.career_plan_result,
            summary=run.summary,
            completed_steps=run.completed_steps or [],
        )

    @staticmethod
    async def list_plans(
        db: AsyncSession,
        user_id: str,
    ) -> CareerPlanningHistoryResponse:
        """列出当前用户的职业规划历史摘要。

        Repository 已限定 `career_planning` 类型；这里将 ORM 记录转换成轻量历史项，
        不返回各节点完整 JSON，从而控制列表响应体积。
        """
        runs = await WorkflowRepo.list_career_plans(db, user_id)

        plans = [
            CareerPlanningHistoryItem(
                run_id=run.id,
                status=run.status,
                progress=run.progress or 0.0,
                target_position=(run.input_data or {}).get("target_position"),
                summary=run.summary,
                error_code=run.error_code,
                created_at=run.created_at,
                completed_at=run.completed_at,
            )
            for run in runs
        ]
        return CareerPlanningHistoryResponse(plans=plans, total=len(plans))

    @staticmethod
    async def delete_plan(
        db: AsyncSession,
        user_id: str,
        run_id: str,
    ) -> None:
        """删除当前用户的一条职业规划及其 LangGraph checkpoint。

        先通过用户 ID 和工作流类型校验所有权，再删除 `workflow_runs` 业务记录；如果该
        记录有关联 `thread_id`，同时清理 SQLite checkpointer，避免遗留孤立运行状态。
        """
        run = await WorkflowRepo.get_plan_by_id_and_user(db, run_id, user_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        thread_id = run.thread_id
        await WorkflowRepo.delete(db, run)
        if thread_id:
            await delete_checkpoint(thread_id)
