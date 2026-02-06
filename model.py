from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

from openai import OpenAI

from storage import load_api_key as load_api_key_from_db
from storage import save_api_key as save_api_key_to_db

API_BASE_URL = "https://api.siliconflow.cn/v1"
MODEL_NAME = "deepseek-ai/DeepSeek-V3.2"

SYSTEM_PROMPT = (
    "你是一个任务拆解助手。\n\n"
    "你的职责是：把用户给出的“模糊想法、目标或计划”，整理为**今天可以执行的具体任务列表**。\n\n"
    "请严格遵守以下规则：\n\n"
    "1. 只输出 JSON，不要输出任何解释性文字。\n"
    "2. JSON 必须是一个数组，每一项表示一个任务对象。\n"
    "3. 每个任务对象必须且只能包含以下字段：\n"
    '   - "text": string，任务的具体描述\n'
    '   - "done": boolean，初始一律为 false\n'
    '   - "pinned": boolean，最多只能有一个任务为 true，其余为 false\n'
    "4. 任务应当是：\n"
    "   - 可执行的\n"
    "   - 具体的\n"
    "   - 适合在“今天”完成的\n"
    "5. 如果用户输入过于宏观或抽象，请你主动拆解为多个小任务。\n"
    "6. 如果任务存在逻辑顺序，请将“最优先/第一步”的任务设为 pinned = true。\n"
    "7. 任务数量建议在 3–7 条之间，避免过多或过少。\n"
    "8. 不要使用编号、emoji 或 markdown 语法。\n"
    "9. 任务描述使用简体中文、动词开头，避免空泛表述（如“努力”“思考一下”等）。"
)


@dataclass
class TaskPayload:
    text: str
    done: bool
    pinned: bool


def load_api_key() -> Optional[str]:
    return load_api_key_from_db()


def save_api_key(api_key: str) -> None:
    save_api_key_to_db(api_key)


def summarize_tasks(user_input: str, api_key: str) -> Tuple[List[TaskPayload], str]:
    client = OpenAI(api_key=api_key, base_url=API_BASE_URL)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ],
    )

    content = response.choices[0].message.content or ""
    try:
        tasks = _parse_tasks(content)
    except ValueError as exc:
        raise ValueError(f"{exc}\n原始返回：{content}") from exc
    return tasks, content


def _parse_tasks(raw_json: str) -> List[TaskPayload]:
    cleaned_json = _extract_json_payload(raw_json)
    data = json.loads(cleaned_json)
    data = _normalize_tasks_data(data)

    pinned_count = 0
    tasks: List[TaskPayload] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("任务项不是对象。")
        if set(item.keys()) != {"text", "done", "pinned"}:
            raise ValueError("任务字段不符合要求。")
        text = item.get("text")
        done = item.get("done")
        pinned = item.get("pinned")
        if not isinstance(text, str):
            raise ValueError("任务 text 必须是字符串。")
        if not isinstance(done, bool) or not isinstance(pinned, bool):
            raise ValueError("任务 done/pinned 必须是布尔值。")
        if pinned:
            pinned_count += 1
        tasks.append(TaskPayload(text=text.strip(), done=done, pinned=pinned))

    if pinned_count > 1:
        raise ValueError("任务置顶数量超过 1。")

    return tasks


def _extract_json_payload(raw: str) -> str:
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    for open_char, close_char in (("[", "]"), ("{", "}")):
        start = raw.find(open_char)
        end = raw.rfind(close_char)
        if start != -1 and end != -1 and end > start:
            candidate = raw[start : end + 1].strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    return raw


def _normalize_tasks_data(data: object) -> List[object]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if set(data.keys()) == {"text", "done", "pinned"}:
            return [data]
        for key in ("tasks", "items", "data", "list"):
            if key in data and isinstance(data[key], list):
                return data[key]
        raise ValueError(f"返回 JSON 不是任务数组，包含字段：{', '.join(data.keys())}")
    raise ValueError("返回的 JSON 不是数组。")
