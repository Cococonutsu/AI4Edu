"""`analyze_problem`：分析题目、验算、独立复核并初始化辅导状态。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from pydantic import ValidationError

from ai4edu.llm.format import image_data_url
from ai4edu.llm.stream import LLMJsonError, JsonResult, complete_json
from ai4edu.storage.repos import attachments, problems
from ai4edu.tools.base import BaseTool, ToolContext, ToolResult
from ai4edu.tools.math_engine import run as run_math
from ai4edu.tutoring.policy import start_problem
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.prompt_builder import (
    build_analyzer_prompt,
    build_solver_check_prompt,
)

_VALIDATION_RETRY_MESSAGE = (
    "上面的输出无法通过校验：{error}。"
    "请修正后重新只输出一个完整的 JSON 对象，不要输出其他文字。"
)


def _read_image(ctx: ToolContext, file_path: str) -> bytes:
    root = ctx.settings.uploads_dir.resolve()
    path = (root / file_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("附件路径不合法")
    return path.read_bytes()


def _image_blocks(images: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "image_url",
            "image_url": {"url": image_data_url(mime_type, data)},
        }
        for mime_type, data in images
    ]


def _user_content(images: list[tuple[str, bytes]], text: str) -> Any:
    if not images:
        return text
    content = _image_blocks(images)
    if text:
        content.append({"type": "text", "text": text})
    return content


async def _call_json(
    ctx: ToolContext,
    *,
    purpose: str,
    model: str,
    prompt_version: str,
    messages: list[dict[str, Any]],
) -> tuple[JsonResult | None, str | None]:
    started = time.perf_counter()
    try:
        # 题目模型较长且模型会先思考，8192 时实测会截断。
        result = await complete_json(
            ctx.client, model=model, messages=messages, max_tokens=16384
        )
    except LLMJsonError as exc:
        await ctx.log_llm_call(
            purpose=purpose,
            model=model,
            prompt_version=prompt_version,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=f"JSON 解析失败：{exc.raw[:300]}",
        )
        return None, "模型输出不是合法 JSON"
    except Exception as exc:
        await ctx.log_llm_call(
            purpose=purpose,
            model=model,
            prompt_version=prompt_version,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc)[:500],
        )
        return None, f"模型调用失败：{exc}"

    await ctx.log_llm_call(
        purpose=purpose,
        model=model,
        prompt_version=prompt_version,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return result, None


def _validation_error_message(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors()[:8]:
        location = ".".join(str(item) for item in error.get("loc", ()))
        parts.append(f"{location}: {error.get('msg')}")
    return "；".join(parts) or str(exc)


async def _analyze(
    ctx: ToolContext,
    *,
    messages: list[dict[str, Any]],
    system_prompt: str,
    grade_band: str,
) -> tuple[ProblemModel | None, str | None]:
    request_messages = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]
    model = ctx.settings.llm_model_analyzer

    for attempt in range(2):
        result, error = await _call_json(
            ctx,
            purpose="analyzer",
            model=model,
            prompt_version=ctx.config.analyzer_version,
            messages=request_messages,
        )
        if result is None:
            if attempt == 0 and error == "模型输出不是合法 JSON":
                request_messages = [
                    *request_messages,
                    {
                        "role": "user",
                        "content": (
                            "上一条输出不是合法的 JSON 对象。"
                            "请重新只输出一个完整的 JSON 对象，不要输出其他文字或代码块标记。"
                        ),
                    },
                ]
                continue
            return None, error

        data = dict(result.data)
        # 学段由学生账号决定，不依赖模型填写（模型常写成"初中"或漏填）。
        data["grade_band"] = grade_band
        try:
            return ProblemModel.model_validate(data), None
        except ValidationError as exc:
            if attempt == 1:
                return None, "题目模型校验失败：" + _validation_error_message(exc)
            error_text = _validation_error_message(exc)
            request_messages = [
                *request_messages,
                {"role": "assistant", "content": result.raw},
                {
                    "role": "user",
                    "content": _VALIDATION_RETRY_MESSAGE.format(error=error_text),
                },
            ]

    return None, "题目模型生成失败"


def _option_letters(*texts: str) -> set[str]:
    letters: set[str] = set()
    for text in texts:
        if not text:
            continue
        letters.update(re.findall(r"(?<![A-Za-z])([A-D])(?![A-Za-z])", text))
    return letters


def _answer_candidates(*texts: str) -> list[str]:
    candidates: list[str] = []
    for text in texts:
        if not text:
            continue
        cleaned = (
            text.replace("$", "")
            .replace("\\(", "")
            .replace("\\)", "")
            .replace("\\[", "")
            .replace("\\]", "")
            .strip()
        )
        for part in re.split(r"[，,；;。\n]", cleaned):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                right = part.split("=", 1)[1].strip()
                if right:
                    candidates.append(right)
                continue
            candidates.append(part)

    unique: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or re.fullmatch(r"[A-D]", candidate):
            continue
        if candidate not in unique:
            unique.append(candidate)
    return unique[:4]


def _normalize_answer(text: str) -> str:
    normalized = text.replace("$", "").replace("\\left", "").replace("\\right", "")
    normalized = re.sub(r"[\s{}]", "", normalized)
    return normalized.strip()


async def _answers_consistent(
    problem: ProblemModel,
    solver_text: str,
    solver_latex: str,
) -> bool:
    problem_letters = _option_letters(problem.answer.text, problem.answer.latex or "")
    solver_letters = _option_letters(solver_text, solver_latex)
    if problem_letters and solver_letters:
        return bool(problem_letters & solver_letters)

    problem_candidates = _answer_candidates(
        problem.answer.latex or "", problem.answer.text
    )
    solver_candidates = _answer_candidates(solver_latex, solver_text)
    if problem_candidates and solver_candidates:
        operations: list[dict[str, Any]] = []
        pairs: list[tuple[str, str]] = []
        for left in problem_candidates:
            for right in solver_candidates:
                operations.append({"kind": "equal", "left": left, "right": right})
                pairs.append((left, right))
        results = await run_math(operations)
        if any(result.get("ok") for result in results):
            return True
        if all(result.get("error") is None for result in results):
            return False

    problem_normalized = {
        _normalize_answer(problem.answer.text),
        _normalize_answer(problem.answer.latex or ""),
    }
    solver_normalized = {
        _normalize_answer(solver_text),
        _normalize_answer(solver_latex),
    }
    problem_normalized.discard("")
    solver_normalized.discard("")
    return bool(problem_normalized & solver_normalized)


async def _solver_check_raw(
    ctx: ToolContext,
    *,
    images: list[tuple[str, bytes]],
    statement: str,
) -> tuple[str, str] | None:
    """独立求解一次，返回 (answer_text, answer_latex)；失败返回 None。

    与题目分析并行执行，所以只用学生原图和原文，不依赖分析器识别出的题干。
    """

    prompt = build_solver_check_prompt(ctx.config, statement=statement)
    messages = [{"role": "user", "content": _user_content(images, prompt)}]
    result, _error = await _call_json(
        ctx,
        purpose="solver_check",
        model=ctx.settings.llm_model_analyzer,
        prompt_version=ctx.config.solver_check_version,
        messages=messages,
    )
    if result is None:
        return None
    solver_text = str(result.data.get("answer_text") or "")
    solver_latex = str(result.data.get("answer_latex") or "")
    if not solver_text and not solver_latex:
        return None
    return solver_text, solver_latex


async def _solver_agrees(
    problem: ProblemModel, solver_task: "asyncio.Task[tuple[str, str] | None]"
) -> bool:
    try:
        answer = await solver_task
    except asyncio.CancelledError:
        raise
    except Exception:
        return False
    if answer is None:
        return False
    return await _answers_consistent(problem, *answer)


async def _checks_pass(problem: ProblemModel) -> bool:
    for check in problem.checks:
        if check.kind == "solve":
            operations = [
                {
                    "kind": "solve",
                    "equation": check.equation,
                    "symbol": check.symbol,
                    "expect": check.expect,
                }
            ]
        else:
            operations = [
                {"kind": "equal", "left": check.left, "right": check.right}
            ]
        results = await run_math(operations)
        if not results or not results[0].get("ok"):
            return False
    return True


class AnalyzeProblemTool(BaseTool):
    name = "analyze_problem"
    description = (
        "学生发来一道需要多步推理的完整题目（文字或图片）时调用。"
        "内部会识别题目、拆分子任务并开始辅导；返回后请用一句话复述题目要求，"
        "然后围绕当前子任务提出第一个问题。"
    )
    running_label = "正在读题…"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "problem_text": {
                "type": "string",
                "description": "模型转述的题目文字；学生已发图片时可留空。",
            },
            "attachment_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "题目图片的附件 id；默认使用学生本回合发送的图片。",
            },
        },
    }

    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        problem_text = str(input.get("problem_text") or "").strip()
        raw_ids = input.get("attachment_ids")
        if raw_ids is None:
            attachment_ids = list(ctx.attachment_ids)
        elif isinstance(raw_ids, list) and all(
            isinstance(item, int) for item in raw_ids
        ):
            attachment_ids = list(dict.fromkeys(raw_ids))
        else:
            return ToolResult(
                content="attachment_ids 必须是整数数组",
                is_error=True,
                status_label="读题失败",
            )

        rows = await attachments.list_by_ids(ctx.db, attachment_ids, ctx.user.id)
        if len(rows) != len(attachment_ids):
            return ToolResult(
                content="部分图片不存在或不属于当前学生，请让学生重新发送图片。",
                is_error=True,
                status_label="读题失败",
            )
        for row in rows:
            if row.conversation_id is not None and row.conversation_id != ctx.conversation_id:
                return ToolResult(
                    content="图片不属于当前会话，请让学生重新发送图片。",
                    is_error=True,
                    status_label="读题失败",
                )

        images: list[tuple[str, bytes]] = []
        for row in rows:
            try:
                images.append((row.mime_type, _read_image(ctx, row.file_path)))
            except OSError:
                return ToolResult(
                    content="图片文件读取失败，请让学生重新发送图片。",
                    is_error=True,
                    status_label="读题失败",
                )

        student_text = ctx.student_text.strip()
        if not images and not student_text and not problem_text:
            return ToolResult(
                content="没有可分析的题目内容，请让学生发送题目文字或图片。",
                is_error=True,
                status_label="读题失败",
            )

        text_parts: list[str] = []
        if student_text:
            text_parts.append(f"学生原文：{student_text}")
        if problem_text:
            text_parts.append(f"学生补充的题目文字：{problem_text}")
        text_parts.append("请根据以上内容生成题目模型。")
        analyzer_text = "\n\n".join(text_parts)

        system_prompt = build_analyzer_prompt(
            ctx.config, grade=ctx.user.grade, grade_band=ctx.user.grade_band
        )
        messages = [
            {"role": "user", "content": _user_content(images, analyzer_text)}
        ]

        # 独立复核与分析同时开始：复核只需要图片和学生原文，不依赖分析结果。
        solver_task = asyncio.create_task(
            _solver_check_raw(ctx, images=images, statement=analyzer_text)
        )
        try:
            problem, error = await _analyze(
                ctx,
                messages=messages,
                system_prompt=system_prompt,
                grade_band=ctx.user.grade_band,
            )
        except BaseException:
            # 包括回合被停止（CancelledError）：不留下孤立的复核任务。
            solver_task.cancel()
            raise
        if problem is None:
            solver_task.cancel()
            return ToolResult(
                content=(
                    "题目识别失败，请让学生发送更清晰的照片或文字。"
                    + (f"（内部原因：{error}）" if error else "")
                ),
                is_error=True,
                status_label="读题失败",
            )

        checks_ok = await _checks_pass(problem)
        solver_ok = await _solver_agrees(problem, solver_task)

        if checks_ok and solver_ok:
            confidence = "verified"
        elif checks_ok or solver_ok:
            confidence = "consistent"
        else:
            confidence = "uncertain"

        record = await problems.add(
            ctx.db,
            conversation_id=ctx.conversation_id,
            model_json=problem.model_dump(mode="json"),
            confidence=confidence,
            framework_version=ctx.config.framework.version,
        )
        await ctx.db.commit()

        new_state = start_problem(problem, record.id, ctx.config)
        ctx.problem = problem
        await ctx.persist_state(new_state)

        if confidence == "uncertain":
            instruction = (
                "如实告诉学生你对这道题的解法没有十足把握，"
                "请学生核对题目是否识别正确，再开始引导。"
            )
        else:
            instruction = "用一句话复述题目要求，然后围绕当前子任务提出第一个问题。"

        payload = {
            "problem_id": record.id,
            "confidence": confidence,
            "statement": problem.statement,
            "goal": problem.goal,
            "subtasks": [
                {"id": subtask.id, "title": subtask.title, "goal": subtask.goal}
                for subtask in problem.subtasks
            ],
            "current_subtask_id": new_state.active_subtask_id,
            "instruction": instruction,
        }
        return ToolResult(
            content=json.dumps(payload, ensure_ascii=False),
            status_label="题目分析完成",
        )


analyze_problem = AnalyzeProblemTool()
