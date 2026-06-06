"""数据源采集器注册表。"""

from .company_site import CompanySiteCollector
from .job51 import Job51Collector
from .job51_xbrowser import Job51XBrowserCollector

__all__ = ["CompanySiteCollector", "Job51Collector", "Job51XBrowserCollector"]
