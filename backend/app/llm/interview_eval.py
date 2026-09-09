# CareerMind AI Interview Evaluation
from app.llm.llm_client import llm_json_call

INTERVIEW_EVAL_SYSTEM_PROMPT = """你是资深面试评估专家。评估候选人对面试题的回答。

只返回一个符合以下结构的有效 JSON 对象：
{
    "score": 7.5,
    "strengths": ["回答中的优点一", "回答中的优点二"],
    "improvements": ["需要改进之处一", "需要改进之处二"],
    "model_answer": "更完整、准确的中文参考答案",
    "comments": "中文总体评价",
    "follow_up_question": ""
}

评分指南（0-10）：
- 10：完美。全面、结构化，有具体例子。
- 8-9：优秀。结构良好，基本完整，例子好。
- 6-7：良好。覆盖要点但缺乏深度或结构。
- 4-5：一般。有些有效观点但明显有缺口。
- 2-3：薄弱。理解肤浅，缺口多。
- 0-1：差。完全跑题或没有相关回答。

行为/HR 题评估：清晰度、结构（STAR 法）、相关性、自我认知。
技术题评估：准确性、深度、实践理解、讲解能力。
系统设计题评估：需求收集、架构、权衡、可扩展性考虑。

追问规则：
- 仅当调用方允许追问且评分低于 7 分时生成 follow_up_question。
- 0–3.9 分：生成基础澄清型追问，帮助补充核心概念或纠正明显误解。
- 4–6.9 分：生成缺失细节型追问，要求补充原理、步骤、取舍或具体案例。
- 7–10 分或调用方不允许追问：follow_up_question 必须为空字符串。
- 追问必须紧扣当前问题和回答，不能重复原题，必须使用简体中文。

所有 strengths、improvements、model_answer 和 comments 必须使用简体中文；技术专有名词可以保留英文。"""

async def evaluate_answer(
    question: str,
    answer: str,
    interview_type: str,
    question_category: str = "general",
    allow_follow_up: bool = True,
) -> dict:
    """评估回答，并在允许且低于阈值时同时生成一次候选追问。"""
    user_prompt = f"""评估该面试回答：

面试类型：{interview_type}
问题类别：{question_category}

问题：
{question}

候选人回答：
{answer}

本次是否允许追问：{"是" if allow_follow_up else "否"}

给出详细评估，包括分数、优点、改进点、参考答案和总体点评；
严格根据评分与“是否允许追问”设置 follow_up_question。"""

    return await llm_json_call(
        system_prompt=INTERVIEW_EVAL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.3,
        operation="interview_evaluation",
    )
