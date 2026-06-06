"""质量报告：统计字段缺失率、解析成功率、重复率。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import NormalizedJob, QualityReport, RawJob


def generate_quality_report(
    raw_jobs: list[RawJob],
    normalized: list[NormalizedJob],
    source: str,
    *,
    duration_seconds: float = 0.0,
) -> QualityReport:
    """从 raw + normalized 生成质量报告。"""
    date_str = datetime.now().strftime("%Y-%m-%d")

    report = QualityReport(
        source=source,
        date=date_str,
        raw_count=len(raw_jobs),
        normalized_count=len(normalized),
        total_duration_seconds=duration_seconds,
    )

    if not raw_jobs:
        return report

    # 状态分布
    for raw in raw_jobs:
        status = raw.source_platform_status or "other"
        if status == "ok":
            report.status_ok += 1
        elif status == "blocked":
            report.status_blocked += 1
        elif status == "parse_error":
            report.status_parse_error += 1
        elif status == "not_found":
            report.status_not_found += 1
        else:
            report.status_other += 1

    report.failed_count = (
        report.status_blocked + report.status_parse_error
        + report.status_not_found + report.status_other
    )

    # 字段缺失率（基于成功采集的 raw）
    ok_jobs = [r for r in raw_jobs if r.source_platform_status == "ok"]
    if ok_jobs:
        total = len(ok_jobs)
        report.missing_title = sum(1 for r in ok_jobs if not r.raw_title.strip()) / total
        report.missing_company = sum(1 for r in ok_jobs if not r.raw_company.strip()) / total
        report.missing_salary = sum(1 for r in ok_jobs if not r.raw_salary.strip()) / total
        report.missing_source_url = sum(1 for r in ok_jobs if not r.source_url.strip()) / total
        report.missing_district = (
            sum(1 for r in ok_jobs if "·" not in (r.raw_location or "")) / total
        )

    # 薪资解析成功率（salary_text 非空即认为有薪资）
    if normalized:
        has_salary = sum(1 for n in normalized if n.salary_text.strip())
        report.salary_parse_success_rate = has_salary / len(normalized)

    # 去重统计（基于 source_url）
    unique_urls = set()
    for n in normalized:
        if n.source_url:
            unique_urls.add(n.source_url)
    report.duplicate_count = max(0, len(normalized) - len(unique_urls))

    # 查询数
    query_keys = set()
    for raw in raw_jobs:
        q = raw.query
        if q:
            city_val = q.get("city", "")
            kw_val = q.get("keyword", "")
            pg_val = q.get("page", 0)
            key = "{}|{}|{}|{}".format(raw.source, city_val, kw_val, pg_val)
            query_keys.add(key)
    report.query_count = len(query_keys)

    return report


def save_report(report: QualityReport, reports_dir: Path) -> Path:
    """保存质量报告为 JSON。"""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "quality_{}_{}.json".format(report.source, report.date)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


SEP = "=" * 50


def print_report(report: QualityReport) -> None:
    """终端输出质量报告摘要。"""
    d = report.to_dict()
    mr = d["missing_rates"]
    sc = d["status_counts"]

    print()
    print(SEP)
    print("质量报告: {}  {}".format(report.source, report.date))
    print(SEP)
    print("  raw: {} | normalized: {} | failed: {}".format(
        report.raw_count, report.normalized_count, report.failed_count))
    print("  duplicates: {} | queries: {}".format(
        report.duplicate_count, report.query_count))
    print("  duration: {:.1f}s".format(report.total_duration_seconds))
    print()
    print("  字段缺失率:")
    print("    title:      {:.1%}".format(mr["title"]))
    print("    company:    {:.1%}".format(mr["company_name"]))
    print("    salary:     {:.1%}".format(mr["salary_text"]))
    print("    source_url: {:.1%}".format(mr["source_url"]))
    print("    district:   {:.1%}".format(mr["district"]))
    print("  薪资解析成功率: {:.1%}".format(d["salary_parse_success_rate"]))
    print("  状态分布: ok={} blocked={} parse_error={} not_found={} other={}".format(
        report.status_ok, report.status_blocked, report.status_parse_error,
        report.status_not_found, report.status_other))
    print(SEP)
