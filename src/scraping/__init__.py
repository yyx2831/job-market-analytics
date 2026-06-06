"""采集框架：通用基类、数据模型、管道、质量报告、多数据源。"""

from .models import NormalizedJob, RawJob, QualityReport, ScrapeQuery

__all__ = ["NormalizedJob", "RawJob", "QualityReport", "ScrapeQuery"]
