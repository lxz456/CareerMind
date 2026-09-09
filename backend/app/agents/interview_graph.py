"""路径 B：可中断、可恢复、自适应难度的模拟面试 LangGraph。

主流程：
START -> initialize -> prepare_question -> ask_question -> wait_for_answer
                                                     (interrupt)
                         decide <- evaluate <- Command(resume=answer)
                           |-- follow_up -------> ask_question
                           |-- next_question ---> prepare_question
                           `-- finish ----------> build_report -> END
"""
import uuid
import re
from collections import Counter
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents.state import InterviewState, create_interview_state
from app.config import get_settings
from app.llm.interview_eval import evaluate_answer
from app.memory.checkpoint import get_checkpointer
from app.tools.interview import generate_questions


DIFFICULTY_LEVELS = ("easy", "medium", "hard")
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def adjust_difficulty(current: str, score: float) -> str:
    """根据一道基础题轮次的得分，计算下一题难度。

    `score >= 8` 提高一级，`score < 4` 降低一级，其余保持不变。
    难度始终限制在 `easy -> medium -> hard` 范围内；传入非法难度时按 `medium` 处理。
    """
    try:
        level = DIFFICULTY_LEVELS.index(current)
    except ValueError:
        level = DIFFICULTY_LEVELS.index("medium")
    if score >= 8:
        level += 1
    elif score < 4:
        level -= 1
    return DIFFICULTY_LEVELS[max(0, min(level, len(DIFFICULTY_LEVELS) - 1))]


def _current_turn_score(state: InterviewState) -> float:
    """计算当前基础题轮次的平均分。

    同一 `question_number` 下的基础回答和可选追问回答都纳入平均值，
    结果只用于调整下一道基础题的难度；没有评分时返回 `0.0`。
    """
    question_number = state["current_index"] + 1
    scores = [
        float(item.get("score", 0))
        for item in state.get("feedbacks", [])
        if item.get("question_number") == question_number
    ]
    return sum(scores) / len(scores) if scores else 0.0


async def initialize_session_node(state: InterviewState) -> dict:
    """初始化面试会话，并生成第 1 道基础题。

    该节点只生成一道题，不提前生成整套题目，从而让后续题目能够根据用户表现调整难度。
    返回第一道题和初始计数器状态。
    """
    questions = await generate_questions(
        interview_type=state["interview_type"],
        target_position=state["target_position"],
        difficulty=state["difficulty"],
        question_count=1,
        question_mode=state["question_mode"],
        question_index=0,
    )
    if not questions:
        raise ValueError("未能生成面试题")
    return {
        "questions": questions,
        "current_index": 0,
        "answered_count": 0,
        "follow_up_count": 0,
        "max_follow_ups_per_question": 1,
        "status": "initializing",
    }


async def prepare_question_node(state: InterviewState) -> dict:
    """把 `questions[current_index]` 准备为当前基础题。

    会清空上一轮的追问标记和追问次数，然后把会话置为等待回答。
    如果题目索引越界，则要求路由到 `finish`。
    """
    index = state["current_index"]
    questions = state["questions"]
    if index >= len(questions):
        return {"next_action": "finish"}
    question = dict(questions[index])
    question["is_follow_up"] = False
    question["parent_question_id"] = None
    return {
        "current_question": question,
        "is_follow_up": False,
        "follow_up_count": 0,
        "status": "waiting_answer",
    }


async def ask_question_node(state: InterviewState) -> dict:
    """通知前端当前题目已准备好，并记录 AI 题目消息。

    同时支持基础题和追问，通过 `is_follow_up` 选择不同前端提示文案，
    完成后进入 `wait_for_answer`。
    """
    question = state["current_question"]
    get_stream_writer()({
        "type": "question_ready",
        "message": "追问题目已生成" if state["is_follow_up"] else "下一题已准备好",
    })
    return {
        "messages": [AIMessage(content=question["question"])],
        "status": "waiting_answer",
    }


async def wait_for_answer_node(state: InterviewState) -> dict:
    """暂停 LangGraph，等待用户提交当前题目的回答。

    `interrupt()` 会把题目信息返回给调用端，并通过 SQLite checkpointer 保存中断点。
    后续用 `Command(resume={"answer": ...})` 恢复时，会从中断位置继续，
    校验回答非空后写入 `pending_answer` 和用户消息。
    """
    payload = interrupt({
        "type": "interview_question",
        "session_id": state["session_id"],
        "question": state["current_question"],
        "question_number": state["current_index"] + 1,
        "total_questions": state["total_questions"],
        "is_follow_up": state["is_follow_up"],
    })
    answer = str((payload or {}).get("answer", "")).strip()
    if not answer:
        raise ValueError("回答不能为空")
    get_stream_writer()({"type": "answer_received", "message": "已收到你的回答"})
    return {
        "pending_answer": answer,
        "messages": [HumanMessage(content=answer)],
        "status": "evaluating",
    }


async def evaluate_answer_node(state: InterviewState) -> dict:
    """调用 LLM 评估当前回答，并把结果追加到面试状态。

    评估包含分数、优点、改进点、参考回答和评语，并在本题仍可追问时让同一次
    模型响应附带候选追问。节点还会补充题目 ID、基础题序号、追问关系和难度；
    `answers`/`feedbacks` 通过 reducer 追加，最后清空 `pending_answer`。
    """
    question = state["current_question"]
    answer = state["pending_answer"] or ""
    writer = get_stream_writer()
    writer({"type": "evaluating", "message": "正在评估你的回答"})
    evaluation = await evaluate_answer(
        question=question["question"],
        answer=answer,
        interview_type=state["interview_type"],
        question_category=question.get("category", "general"),
        allow_follow_up=(
            not state["is_follow_up"]
            and state["follow_up_count"] < state["max_follow_ups_per_question"]
        ),
    )
    suggested_follow_up = str(evaluation.pop("follow_up_question", "")).strip()
    if not _CJK_PATTERN.search(suggested_follow_up):
        suggested_follow_up = ""
    feedback = {
        **evaluation,
        "question_id": question["question_id"],
        "question_number": state["current_index"] + 1,
        "question": question["question"],
        "answer": answer,
        "is_follow_up": state["is_follow_up"],
        "parent_question_id": question.get("parent_question_id"),
        "difficulty": question.get("difficulty", state["difficulty"]),
    }
    writer({
        "type": "evaluation_completed",
        "message": f"评分完成：{evaluation.get('score', 0)} 分",
        "score": evaluation.get("score", 0),
    })
    return {
        "answers": [{
            "question_id": question["question_id"],
            "question": question["question"],
            "answer": answer,
            "is_follow_up": state["is_follow_up"],
        }],
        "feedbacks": [feedback],
        "answered_count": state["answered_count"] + 1,
        "pending_answer": None,
        "suggested_follow_up": suggested_follow_up or None,
    }


async def decide_follow_up_node(state: InterviewState) -> dict:
    """根据最新评分决定追问、下一题或结束面试。

    硬规则由代码控制：得分 `>= 7` 直接进入下一题/结束，每道基础题最多追问一次。
    得分低于 7 时使用 `evaluate` 节点同一次 LLM 调用生成的候选追问；候选为空或
    未通过中文校验时跳过追问，不再发起第二次模型请求。
    """
    last_feedback = state["feedbacks"][-1]
    last_base_question = state["current_index"] >= state["total_questions"] - 1
    score = float(last_feedback.get("score", 0))

    # 硬限制：每道基础题最多追问一次，7 分及以上不追问。
    can_follow_up = state["follow_up_count"] < state["max_follow_ups_per_question"]
    if score >= 7 or not can_follow_up:
        action = "finish" if last_base_question else "next_question"
        return {"next_action": action}

    follow_up_style = "基础澄清追问" if score < 4 else "缺失细节追问"
    get_stream_writer()({
        "type": "generating_follow_up",
        "message": f"正在准备{follow_up_style}",
    })

    follow_up_question = (state.get("suggested_follow_up") or "").strip()
    if follow_up_question:
        return {
            "next_action": "follow_up",
            "suggested_follow_up": follow_up_question,
        }

    # LLM 不负责提前结束面试；是否结束由基础题进度决定。
    action = "finish" if last_base_question else "next_question"
    return {
        "next_action": action,
        "suggested_follow_up": None,
    }


async def follow_up_node(state: InterviewState) -> dict:
    """把 LLM 生成的追问转换为可展示的当前题目。

    追问会获得新 UUID，继承基础题的类别和难度，并通过 `parent_question_id`
    与原基础题关联。该节点不增加 `current_index`，所以 UI 中仍属于同一道基础题。
    """
    parent = state["current_question"]
    question = {
        "question_id": str(uuid.uuid4()),
        "question": state["suggested_follow_up"],
        "category": parent.get("category", "general"),
        "difficulty": parent.get("difficulty", state["difficulty"]),
        "is_follow_up": True,
        "parent_question_id": parent.get("parent_question_id") or parent["question_id"],
    }
    return {
        "current_question": question,
        "is_follow_up": True,
        "follow_up_count": state["follow_up_count"] + 1,
        "status": "waiting_answer",
    }


async def next_question_node(state: InterviewState) -> dict:
    """完成当前轮次后，调整难度并生成下一道基础题。

    先对基础回答及其可选追问评分求平均，再通过 `adjust_difficulty()` 得到新难度。
    生成下一题时传入已问题目用于去重，并替换旧版 checkpoint 可能预生成的未问题池。
    返回后由 `prepare_question` 把新题设为 `current_question`。
    """
    next_index = state["current_index"] + 1
    turn_score = _current_turn_score(state)
    next_difficulty = adjust_difficulty(state["difficulty"], turn_score)
    labels = {"easy": "简单", "medium": "中等", "hard": "困难"}
    get_stream_writer()({
        "type": "adapting_difficulty",
        "message": f"根据本题表现，下一题难度为{labels[next_difficulty]}",
        "score": round(turn_score, 1),
        "difficulty": next_difficulty,
    })

    previous_questions = [
        item.get("question", "") for item in state["questions"][:next_index]
    ]
    generated = await generate_questions(
        interview_type=state["interview_type"],
        target_position=state["target_position"],
        difficulty=next_difficulty,
        question_count=1,
        question_mode=state["question_mode"],
        question_index=next_index,
        exclude_questions=previous_questions,
    )
    if not generated:
        raise ValueError("未能生成下一道面试题")
    next_question = generated[0]
    next_question["question_number"] = next_index + 1
    return {
        "difficulty": next_difficulty,
        # 丢弃旧版“一次生成整套题” checkpoint 中尚未使用的题池，改用当前难度生成的新题。
        "questions": state["questions"][:next_index] + [next_question],
        "current_index": next_index,
        "current_question": None,
        "is_follow_up": False,
        "follow_up_count": 0,
    }


async def build_report_node(state: InterviewState) -> dict:
    """用确定性 Python 规则汇总所有评分，构建最终面试报告。

    总分是所有 feedback（包含追问）的平均分；优势和改进点按出现频率取前 3 项。
    该节点不调用 LLM，而是根据总分区间生成表现等级和建议，最后将状态设为 `completed`。
    """
    get_stream_writer()({"type": "building_report", "message": "正在生成面试报告"})
    feedbacks = state.get("feedbacks") or []
    scores = [float(item.get("score", 0)) for item in feedbacks]
    total_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    strengths = Counter(
        item for feedback in feedbacks for item in feedback.get("strengths", [])
    )
    improvements = Counter(
        item for feedback in feedbacks for item in feedback.get("improvements", [])
    )
    top_strengths = [item for item, _ in strengths.most_common(3)]
    top_improvements = [item for item, _ in improvements.most_common(3)]

    if total_score >= 8:
        level, tips = "优秀", ["继续挑战更高难度问题", "加强复杂场景下的表达"]
    elif total_score >= 6:
        level, tips = "良好", ["使用 STAR 方法组织回答", "增加具体项目和数据例子"]
    elif total_score >= 4:
        level, tips = "一般", ["加强基础知识", "对照参考答案进行复盘"]
    else:
        level, tips = "需要提升", ["系统复习岗位基础知识", "从简单题开始进行口头练习"]

    return {
        "status": "completed",
        "next_action": "finish",
        "result": {
            "total_score": total_score,
            "overall_assessment": f"面试表现：{level}（{total_score}/10）。",
            "strengths": top_strengths,
            "areas_to_improve": top_improvements,
            "tips": tips,
        },
    }


def route_decision(state: InterviewState) -> str:
    """读取 `decide_follow_up_node` 写入的路由结果。

    返回值只应为 `follow_up`、`next_question` 或 `finish`；结果为空时默认进入 `finish`。
    """
    return state["next_action"] or "finish"


def build_interview_graph():
    """定义并返回路径 B 的未编译 `StateGraph`。

    该函数注册 9 个节点、主顺序边、`decide` 的三条条件边，
    以及追问/下一题的循环边。此处只定义拓扑，不绑定 checkpointer。
    """
    graph = StateGraph(InterviewState)
    graph.add_node("initialize", initialize_session_node)
    graph.add_node("prepare_question", prepare_question_node)
    graph.add_node("ask_question", ask_question_node)
    graph.add_node("wait_for_answer", wait_for_answer_node)
    graph.add_node("evaluate", evaluate_answer_node)
    graph.add_node("decide", decide_follow_up_node)
    graph.add_node("follow_up", follow_up_node)
    graph.add_node("next_question", next_question_node)
    graph.add_node("build_report", build_report_node)

    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "prepare_question")
    graph.add_edge("prepare_question", "ask_question")
    graph.add_edge("ask_question", "wait_for_answer")
    graph.add_edge("wait_for_answer", "evaluate")
    graph.add_edge("evaluate", "decide")
    graph.add_conditional_edges("decide", route_decision, {
        "follow_up": "follow_up",
        "next_question": "next_question",
        "finish": "build_report",
    })
    graph.add_edge("follow_up", "ask_question")
    graph.add_edge("next_question", "prepare_question")
    graph.add_edge("build_report", END)
    return graph


interview_graph = None


def init_interview_graph():
    """在应用启动且 SQLite checkpointer 打开后，编译路径 B。

    编译后的图保存在模块级 `interview_graph` 中供所有请求复用，
    checkpointer 则按 `thread_id` 持久化每个面试会话的状态和中断点。
    """
    global interview_graph
    interview_graph = build_interview_graph().compile(checkpointer=get_checkpointer())
    return interview_graph


def get_interview_graph():
    """获取已编译的路径 B 图实例。

    如果应用 lifespan 尚未调用 `init_interview_graph()`，则抛出错误，
    避免在没有 checkpointer 的情况下运行面试。
    """
    if interview_graph is None:
        raise RuntimeError("Interview graph has not been initialized")
    return interview_graph


def interview_config(session_id: str) -> dict:
    """为一次面试生成 LangGraph 运行配置。

    `session_id` 作为 checkpoint `thread_id`，保证不同面试状态相互隔离；
    `recursion_limit` 从环境配置读取，限制单次图调用的最大节点循环次数，
    防止异常无限循环。
    """
    return {
        "configurable": {"thread_id": session_id},
        "recursion_limit": get_settings().AGENT_RECURSION_LIMIT,
    }


async def get_interview_state(session_id: str) -> dict | None:
    """从 SQLite checkpoint 读取指定面试会话的最新状态。

    存在有效 snapshot 时返回其 `values` 字典，会话不存在或状态为空时返回 `None`。
    """
    snapshot = await get_interview_graph().aget_state(interview_config(session_id))
    return snapshot.values if snapshot and snapshot.values else None


async def start_interview_graph(
    *,
    user_id: str,
    session_id: str,
    interview_type: str,
    target_position: str,
    question_mode: str = "review",
    difficulty: str = "medium",
    total_questions: int = 5,
) -> dict:
    """创建路径 B 的初始状态，并运行到第一道题的中断点。

    该函数是 Service 启动面试时使用的公开入口，统一封装初始状态构造、
    LangGraph 运行配置和首次调用。成功后返回 checkpoint 中的最新完整状态。
    """
    initial_state = create_interview_state(
        user_id=user_id,
        session_id=session_id,
        interview_type=interview_type,
        target_position=target_position,
        question_mode=question_mode,
        difficulty=difficulty,
        total_questions=total_questions,
    )
    await get_interview_graph().ainvoke(initial_state, interview_config(session_id))
    state = await get_interview_state(session_id)
    if not state:
        raise RuntimeError("Interview state unavailable after initialization")
    return state


async def stream_interview_answer(
    session_id: str,
    answer: str,
) -> AsyncIterator[dict]:
    """用用户回答恢复路径 B，并逐个产出 Graph 的自定义流事件。

    `Command(resume=...)` 和 `stream_mode="custom"` 都属于 Graph 运行细节，
    由此处统一管理；Service 只需消费事件并负责业务数据持久化。
    """
    async for event in get_interview_graph().astream(
        Command(resume={"answer": answer}),
        interview_config(session_id),
        stream_mode="custom",
    ):
        yield event
