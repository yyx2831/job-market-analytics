"""数据管道：raw JSONL → 归一化 → 兼容 CSV。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import NormalizedJob, RawJob


# ── JSONL 读取 ──────────────────────────────────────────

def load_raw_jobs(jsonl_path: Path) -> list[RawJob]:
    """从 JSONL 文件中加载原始岗位列表。"""
    jobs: list[RawJob] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            jobs.append(RawJob(
                source=record.get("source", ""),
                source_job_id=record.get("source_job_id", ""),
                source_url=record.get("source_url", ""),
                source_platform_status=record.get("source_platform_status", "ok"),
                raw_title=record.get("raw_title", ""),
                raw_company=record.get("raw_company", ""),
                raw_salary=record.get("raw_salary", ""),
                raw_location=record.get("raw_location", ""),
                raw_experience=record.get("raw_experience", ""),
                raw_education=record.get("raw_education", ""),
                raw_industry=record.get("raw_industry", ""),
                raw_company_size=record.get("raw_company_size", ""),
                raw_financing=record.get("raw_financing", ""),
                raw_skills=record.get("raw_skills", []),
                raw_description=record.get("raw_description", ""),
                raw_publish_time=record.get("raw_publish_time", ""),
                query=record.get("query", {}),
                crawl_time=record.get("crawl_time", ""),
                parser_version=record.get("parser_version", "1.0.0"),
                raw_hash=record.get("raw_hash", ""),
            ))
    return jobs


# ── 位置解析 ────────────────────────────────────────────

def parse_location(raw: str) -> tuple[str, str]:
    """解析 "城市·区域" 格式。"""
    if not raw:
        return "", ""
    if "·" in raw:
        parts = raw.split("·", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    return raw.strip(), ""


# ── 归一化 ──────────────────────────────────────────────

def normalize_job(raw: RawJob) -> NormalizedJob:
    """将 RawJob 转换为 NormalizedJob，兼容现有 CSV schema。"""
    city, district = parse_location(raw.raw_location)

    # 判断必需字段是否缺失
    missing = []
    if not raw.raw_title.strip():
        missing.append("title")
    if not raw.raw_company.strip():
        missing.append("company_name")
    if not raw.source_url.strip():
        missing.append("source_url")

    status = "ok" if not missing else "missing_{}".format("_".join(missing))

    return NormalizedJob(
        source_job_id=raw.source_job_id,
        title=raw.raw_title.strip() or "未知岗位",
        company_name=raw.raw_company.strip() or "未知公司",
        salary_text=raw.raw_salary.strip(),
        city=city or "未知",
        district=district or "未知",
        experience=raw.raw_experience.strip() or "未知",
        education=raw.raw_education.strip() or "未知",
        industry=raw.raw_industry.strip() or "未知",
        company_size=raw.raw_company_size.strip() or "未知",
        financing_stage=raw.raw_financing.strip() or "未知",
        skills=",".join(raw.raw_skills) if raw.raw_skills else "",
        description=raw.raw_description.strip(),
        source=raw.source or "unknown",
        source_url=raw.source_url.strip(),
        publish_time=raw.raw_publish_time.strip(),
        crawl_time=raw.crawl_time,
        normalized_status=status,
        parser_version=raw.parser_version,
    )


def normalize_batch(raw_jobs: list[RawJob]) -> list[NormalizedJob]:
    """批量归一化。跳过采集失败的记录。"""
    normalized = []
    for raw in raw_jobs:
        if raw.source_platform_status not in ("ok",):
            continue
        normalized.append(normalize_job(raw))
    return normalized


# ── CSV 输出 ────────────────────────────────────────────

FIELD_NAMES = [
    "source_job_id", "title", "company_name", "salary_text",
    "city", "district", "experience", "education", "industry",
    "company_size", "financing_stage", "skills", "description",
    "source", "source_url", "publish_time", "crawl_time",
]


def write_csv(normalized: list[NormalizedJob], csv_path: Path) -> int:
    """将归一化岗位写入兼容 CSV 文件。返回写入行数。"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELD_NAMES)
        writer.writeheader()
        for job in normalized:
            writer.writerow({
                "source_job_id": job.source_job_id,
                "title": job.title,
                "company_name": job.company_name,
                "salary_text": job.salary_text,
                "city": job.city,
                "district": job.district,
                "experience": job.experience,
                "education": job.education,
                "industry": job.industry,
                "company_size": job.company_size,
                "financing_stage": job.financing_stage,
                "skills": job.skills,
                "description": job.description,
                "source": job.source,
                "source_url": job.source_url,
                "publish_time": job.publish_time,
                "crawl_time": job.crawl_time,
            })
    return len(normalized)


def pipeline(raw_jsonl: Path, output_csv: Path) -> tuple[int, list[NormalizedJob]]:
    """完整管道：读取 JSONL → 归一化 → 写 CSV。"""
    raw_jobs = load_raw_jobs(raw_jsonl)
    normalized = normalize_batch(raw_jobs)
    count = write_csv(normalized, output_csv)
    return count, normalized
