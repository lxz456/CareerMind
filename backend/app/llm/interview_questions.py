"""面试题生成与候选题选择的纯 LLM 能力。"""
import json
import re

from app.llm.llm_client import llm_json_call


_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


QUESTION_LOCALIZATION_PROMPT = """你是面试题中文本地化专家。
将输入题目的 question、topic 和 expected_points 改写为自然、专业的简体中文。

只返回有效 JSON：
{
    "questions": [
        {
            "question": "中文问题",
            "topic": "中文主题",
            "expected_points": ["中文考察点"]
        }
    ]
}

规则：
- 不改变问题的技术含义、难度或考察范围
- Java、Python、HTTP、RAG、API 等技术专有名词可以保留英文
- 每个 question 必须包含简体中文
- 返回题目数量和顺序必须与输入完全一致"""


async def _ensure_chinese_questions(questions: list[dict]) -> list[dict]:
    """将纯英文题目批量本地化；二次结果仍非中文时拒绝返回。"""
    positions = [
        index
        for index, item in enumerate(questions)
        if not _CJK_PATTERN.search(str(item.get("question", "")))
    ]
    if not positions:
        return questions

    source = [questions[index] for index in positions]
    result = await llm_json_call(
        system_prompt=QUESTION_LOCALIZATION_PROMPT,
        user_prompt="请本地化以下面试题：\n" + json.dumps(source, ensure_ascii=False),
        temperature=0,
        operation="question_localization",
    )
    localized = result.get("questions", [])
    if len(localized) != len(positions):
        raise ValueError("面试题中文本地化返回数量不一致")

    for position, translated in zip(positions, localized):
        question_text = str(translated.get("question", "")).strip()
        if not _CJK_PATTERN.search(question_text):
            raise ValueError("模型返回了非中文面试题")
        questions[position]["question"] = question_text
        if translated.get("topic"):
            questions[position]["topic"] = translated["topic"]
        if translated.get("expected_points"):
            questions[position]["expected_points"] = translated["expected_points"]
    return questions

# ---- HR Interview ----
HR_INTERVIEW_PROMPT = """你是顶级科技公司的资深 HR 面试官。
你的关注点：行为题、项目经验、职业规划、团队契合度、沟通能力。

为候选人生成 {question_count} 道 HR 面试题，目标岗位：{target_position}。
题目难度必须为：{difficulty}。{difficulty_guidance}
不得与以下已经问过的题目重复：{excluded_questions}

只返回一个有效的 JSON 对象：
{{
    "questions": [
        {{
            "question": "请介绍一个你参与过的具有挑战性的项目。",
            "category": "behavioral",
            "difficulty": "{difficulty}",
            "expected_points": ["项目背景", "个人行动", "最终结果"]
        }}
    ]
}}

所有 question 和 expected_points 必须使用简体中文；公司名、产品名和技术专有名词可以保留英文。"""

# ---- Technical Interview ----
TECHNICAL_INTERVIEW_PROMPT = """你是顶级科技公司的资深技术面试官。
你的关注点：技术能力、编码能力、系统知识、问题解决能力。

为目标岗位生成 {question_count} 道技术面试题：{target_position}。

用户已知技能：{skills}
题目难度必须为：{difficulty}。{difficulty_guidance}
不得与以下已经问过的题目重复：{excluded_questions}

只返回一个有效的 JSON 对象：
{{
    "questions": [
        {{
            "question": "请解释 Transformer 中的注意力机制。",
            "category": "technical",
            "topic": "深度学习",
            "difficulty": "{difficulty}",
            "expected_points": ["核心原理", "计算过程", "实际应用"]
        }}
    ]
}}

所有 question、topic 和 expected_points 必须使用简体中文；Java、Python、HTTP、RAG 等技术专有名词可以保留英文。"""

# ---- System Design Interview ----
SYSTEM_DESIGN_PROMPT = """你是主持系统设计面试的首席工程师。
你的关注点：架构设计、可扩展性、权衡取舍、分布式系统。

为目标岗位生成 {question_count} 道系统设计题：{target_position}。
题目难度必须为：{difficulty}。{difficulty_guidance}
不得与以下已经问过的题目重复：{excluded_questions}

只返回一个有效的 JSON 对象：
{{
    "questions": [
        {{
            "question": "请设计一个支持百万用户的实时聊天系统。",
            "category": "system_design",
            "topic": "实时系统",
            "difficulty": "{difficulty}",
            "expected_points": ["需求分析", "核心架构", "扩展性与权衡"]
        }}
    ]
}}

所有 question、topic 和 expected_points 必须使用简体中文；组件名、协议名和技术专有名词可以保留英文。"""

async def generate_questions_by_llm(
    interview_type: str,
    target_position: str,
    skills: list[str],
    question_count: int,
    difficulty: str = "medium",
    exclude_questions: list[str] | None = None,
) -> list[dict]:
    """使用当前配置的大模型直接生成结构化面试题。

    函数先根据 `difficulty` 生成难度说明，再按 `interview_type`
    选择 HR、技术或系统设计提示词。批量生成 `mixed` 类型时，
    会把题目数量分配给三种题型并合并结果。
    `exclude_questions` 会写入提示词，用于尽量避免生成已经问过的题。

    返回原始题目列表，不在此处入库，也不分配 `question_id`。
    """
    skills_str = ", ".join(skills) if skills else "Not specified"
    excluded = "；".join(exclude_questions or []) or "无"
    guidance = {
        "easy": "考查岗位必备基础概念和直接应用，不设置复杂陷阱",
        "medium": "考查实际应用、原理理解和常见权衡",
        "hard": "考查复杂场景、深入原理、边界条件和方案权衡",
    }.get(difficulty, "考查实际应用和原理理解")

    if interview_type == "hr":
        prompt = HR_INTERVIEW_PROMPT.format(
            question_count=question_count, target_position=target_position,
            difficulty=difficulty, difficulty_guidance=guidance,
            excluded_questions=excluded,
        )
    elif interview_type == "technical":
        prompt = TECHNICAL_INTERVIEW_PROMPT.format(
            question_count=question_count, target_position=target_position, skills=skills_str,
            difficulty=difficulty, difficulty_guidance=guidance,
            excluded_questions=excluded,
        )
    elif interview_type == "system_design":
        prompt = SYSTEM_DESIGN_PROMPT.format(
            question_count=question_count, target_position=target_position,
            difficulty=difficulty, difficulty_guidance=guidance,
            excluded_questions=excluded,
        )
    elif interview_type == "mixed":
        hr_count = question_count // 3
        tech_count = question_count // 3
        sd_count = question_count - hr_count - tech_count
        questions = []
        if hr_count:
            hr_prompt = HR_INTERVIEW_PROMPT.format(
                question_count=hr_count, target_position=target_position,
                difficulty=difficulty, difficulty_guidance=guidance,
                excluded_questions=excluded,
            )
            hr_result = await llm_json_call(
                system_prompt=hr_prompt,
                user_prompt="生成 HR 面试题。",
                operation="interview_question_hr",
            )
            questions.extend(hr_result.get("questions", []))
        if tech_count:
            tech_prompt = TECHNICAL_INTERVIEW_PROMPT.format(
                question_count=tech_count, target_position=target_position, skills=skills_str,
                difficulty=difficulty, difficulty_guidance=guidance,
                excluded_questions=excluded,
            )
            tech_result = await llm_json_call(
                system_prompt=tech_prompt,
                user_prompt="生成技术面试题。",
                operation="interview_question_technical",
            )
            questions.extend(tech_result.get("questions", []))
        if sd_count:
            sd_prompt = SYSTEM_DESIGN_PROMPT.format(
                question_count=sd_count, target_position=target_position,
                difficulty=difficulty, difficulty_guidance=guidance,
                excluded_questions=excluded,
            )
            sd_result = await llm_json_call(
                system_prompt=sd_prompt,
                user_prompt="生成系统设计题。",
                operation="interview_question_system_design",
            )
            questions.extend(sd_result.get("questions", []))
        _force_difficulty(questions, difficulty)
        return await _ensure_chinese_questions(questions)

    result = await llm_json_call(
        system_prompt=prompt,
        user_prompt=f"生成 {question_count} 道 {interview_type} 面试题。",
        operation="interview_question_generation",
    )
    questions = result.get("questions", [])
    _force_difficulty(questions, difficulty)
    return await _ensure_chinese_questions(questions)


def _force_difficulty(questions: list[dict], difficulty: str) -> None:
    """将所有题目的难度强制改为工作流当前指定的难度。

    这是一道保护层：即使旧 RAG 题目或 LLM 返回了其他难度，
    最终仍以 LangGraph 的自适应难度决策为准。函数直接修改传入列表，无返回值。
    """
    for question in questions:
        question["difficulty"] = difficulty
