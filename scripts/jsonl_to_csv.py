"""将 mock raw JSONL 转换为兼容数据库的 CSV 格式。

处理思路：
- raw_location "成都·高新区" → city="成都", district="高新区"
- raw_skills 数组 → 逗号分隔字符串
- 保留 source、crawl_time 等采集元数据
- 输出 CSV 与 src/database.py 的 import_csv 完全兼容
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


def parse_location(raw: str) -> tuple[str, str]:
    """解析 "城市·区域" 格式的原始位置字段。"""
    if "·" in raw:
        parts = raw.split("·", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else "未知"
    return raw.strip(), "未知"


def jsonl_to_csv(jsonl_path: Path, csv_path: Path) -> int:
    """将 JSONL 转换为 CSV，返回写入行数。"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "source_job_id",
        "title",
        "company_name",
        "salary_text",
        "city",
        "district",
        "experience",
        "education",
        "industry",
        "company_size",
        "financing_stage",
        "skills",
        "description",
        "source",
        "source_url",
        "publish_time",
        "crawl_time",
    ]

    count = 0
    with jsonl_path.open("r", encoding="utf-8") as infile, \
         csv_path.open("w", newline="", encoding="utf-8") as outfile:

        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for line in infile:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            city, district = parse_location(record.get("raw_location", ""))

            writer.writerow({
                "source_job_id": record.get("source_job_id", ""),
                "title": record.get("raw_title", "未知岗位"),
                "company_name": record.get("raw_company", "未知公司"),
                "salary_text": record.get("raw_salary", ""),
                "city": city,
                "district": district,
                "experience": record.get("raw_experience", "未知"),
                "education": record.get("raw_education", "未知"),
                "industry": record.get("raw_industry", "未知"),
                "company_size": record.get("raw_company_size", "未知"),
                "financing_stage": record.get("raw_financing", "未知"),
                "skills": ",".join(record.get("raw_skills", [])),
                "description": record.get("raw_description", ""),
                "source": record.get("source", "unknown"),
                "source_url": record.get("raw_url", ""),
                "publish_time": record.get("raw_publish_time", ""),
                "crawl_time": record.get("crawl_time", ""),
            })
            count += 1

    return count


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    jsonl_path = root / "data" / "raw" / "mock_jobs.jsonl"
    csv_path = root / "data" / "raw" / "mock_jobs.csv"
    if not jsonl_path.exists():
        print(f"JSONL not found: {jsonl_path}")
        raise SystemExit(1)
    count = jsonl_to_csv(jsonl_path, csv_path)
    print(f"Converted {count} records: {jsonl_path} → {csv_path}")
