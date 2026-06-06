from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from .skill_dict import SKILL_KEYWORDS


def parse_salary(salary_text: str | None) -> dict[str, float | int | str | None]:
    text = (salary_text or "").strip()
    if not text or "面议" in text:
        return {
            "salary_min": None,
            "salary_max": None,
            "salary_avg": None,
            "salary_months": None,
            "salary_unit": "unknown",
        }

    normalized = text.upper().replace("Ｋ", "K").replace("－", "-").replace("—", "-")
    months = 12
    month_match = re.search(r"[·xX*](\d{2})薪", normalized)
    if month_match:
        months = int(month_match.group(1))

    unit = "month"
    if "元/天" in normalized or "/天" in normalized:
        unit = "day"
    elif "元/时" in normalized or "/时" in normalized:
        unit = "hour"
    elif "万/年" in normalized or "W/年" in normalized:
        unit = "year"

    tokens = re.findall(r"(\d+(?:\.\d+)?)(K|W|千|万)?", normalized)
    if not tokens:
        return {
            "salary_min": None,
            "salary_max": None,
            "salary_avg": None,
            "salary_months": months,
            "salary_unit": unit,
        }

    common_unit = next((token_unit for _, token_unit in tokens if token_unit), "")

    def to_yuan(number_text: str, token_unit: str) -> float:
        number = float(number_text)
        actual_unit = token_unit or common_unit
        if actual_unit in {"K", "千"}:
            return number * 1000
        if actual_unit in {"W", "万"}:
            return number * 10000
        return number

    values = [to_yuan(number, token_unit) for number, token_unit in tokens[:2]]

    if len(values) == 1:
        salary_min = salary_max = values[0]
    else:
        salary_min, salary_max = min(values[0], values[1]), max(values[0], values[1])

    if unit == "year":
        salary_min = salary_min / 12
        salary_max = salary_max / 12

    salary_avg = (salary_min + salary_max) / 2
    return {
        "salary_min": int(round(salary_min)),
        "salary_max": int(round(salary_max)),
        "salary_avg": int(round(salary_avg)),
        "salary_months": months,
        "salary_unit": unit,
    }


def normalize_text(value: str | None, default: str = "未知") -> str:
    value = (value or "").strip()
    return value if value else default


def extract_skills(text_parts: Iterable[str | None]) -> list[str]:
    haystack = " ".join(part or "" for part in text_parts).lower()
    found = []
    for skill in SKILL_KEYWORDS:
        if skill.lower() in haystack:
            found.append(skill)
    return sorted(set(found), key=found.index)


def canonical_job_key(row: dict[str, str]) -> str:
    source = normalize_text(row.get("source"), "").lower()
    source_job_id = normalize_text(row.get("source_job_id"), "").lower()
    if source and source_job_id:
        return f"{source}|{source_job_id}"

    source_url = normalize_text(row.get("source_url"), "").lower().rstrip("/")
    if source and source_url:
        return f"{source}|{source_url}"

    title = normalize_text(row.get("title"), "").lower()
    company = normalize_text(row.get("company_name"), "").lower()
    city = normalize_text(row.get("city"), "").lower()
    district = normalize_text(row.get("district"), "").lower()
    return f"{title}|{company}|{city}|{district}"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")
