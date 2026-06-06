"""采集框架数据结构定义。

所有模型使用 dataclass，避免引入额外依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScrapeQuery:
    """采集任务查询参数。"""
    source: str                              # 数据源标识
    city: str                                # 目标城市
    keyword: str                             # 搜索关键词
    page: int = 1                            # 当前页码
    search_url: str = ""                     # 实际请求的 URL（用于日志）
    fetched_at: str = ""                     # 采集时间 ISO

    @property
    def task_key(self) -> str:
        """断点续跑的进度标识。"""
        return f"{self.source}|{self.city}|{self.keyword}|{self.page}"


@dataclass
class RawJob:
    """爬虫产出的原始岗位数据，未清洗。"""
    source: str                              # 数据源
    source_job_id: str = ""                  # 平台原始 ID
    source_url: str = ""                     # 岗位链接
    source_platform_status: str = "ok"       # 采集状态: ok/blocked/not_found/parse_error

    # 原始提取字段
    raw_title: str = ""
    raw_company: str = ""
    raw_salary: str = ""
    raw_location: str = ""
    raw_experience: str = ""
    raw_education: str = ""
    raw_industry: str = ""
    raw_company_size: str = ""
    raw_financing: str = ""
    raw_skills: list[str] = field(default_factory=list)
    raw_description: str = ""
    raw_publish_time: str = ""

    # 采集元数据
    query: dict = field(default_factory=dict)    # 触发本条记录的查询参数
    crawl_time: str = ""                         # 采集时间
    parser_version: str = "1.0.0"                # 解析器版本
    raw_hash: str = ""                           # 原始内容 hash


@dataclass
class NormalizedJob:
    """归一化后的岗位数据，兼容现有 CSV schema。"""
    source_job_id: str
    title: str
    company_name: str
    salary_text: str
    city: str
    district: str
    experience: str
    education: str
    industry: str
    company_size: str
    financing_stage: str
    skills: str                    # 逗号分隔
    description: str
    source: str
    source_url: str
    publish_time: str
    crawl_time: str

    # 归一化状态
    normalized_status: str = "ok"  # ok/missing_required_field
    parser_version: str = "1.0.0"


@dataclass
class QualityReport:
    """单次采集任务的质量报告。"""
    source: str
    date: str
    raw_count: int = 0
    normalized_count: int = 0
    failed_count: int = 0
    duplicate_count: int = 0

    # 字段缺失率 (0.0 ~ 1.0)
    missing_title: float = 0.0
    missing_company: float = 0.0
    missing_salary: float = 0.0
    missing_source_url: float = 0.0
    missing_district: float = 0.0

    # 解析成功率
    salary_parse_success_rate: float = 0.0

    # 状态分布
    status_ok: int = 0
    status_blocked: int = 0
    status_parse_error: int = 0
    status_not_found: int = 0
    status_other: int = 0

    # 元数据
    query_count: int = 0
    total_duration_seconds: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().replace(microsecond=0).isoformat(sep=" "))

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "date": self.date,
            "raw_count": self.raw_count,
            "normalized_count": self.normalized_count,
            "failed_count": self.failed_count,
            "duplicate_count": self.duplicate_count,
            "missing_rates": {
                "title": round(self.missing_title, 4),
                "company_name": round(self.missing_company, 4),
                "salary_text": round(self.missing_salary, 4),
                "source_url": round(self.missing_source_url, 4),
                "district": round(self.missing_district, 4),
            },
            "salary_parse_success_rate": round(self.salary_parse_success_rate, 4),
            "status_counts": {
                "ok": self.status_ok,
                "blocked": self.status_blocked,
                "parse_error": self.status_parse_error,
                "not_found": self.status_not_found,
                "other": self.status_other,
            },
            "query_count": self.query_count,
            "total_duration_seconds": round(self.total_duration_seconds, 1),
            "created_at": self.created_at,
        }
