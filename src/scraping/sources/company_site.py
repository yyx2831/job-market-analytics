"""企业官网招聘页采集器。

通过配置站点规则，从企业招聘页面提取岗位信息。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from ..base import BaseCollector
from ..models import RawJob, ScrapeQuery

logger = logging.getLogger("scraping.company_site")


# ── 站点配置 ─────────────────────────────────────────────

# 每个站点定义：入口 URL 模板、列表/详情选择器
SITE_CONFIGS = {
    "meituan": {
        "name": "美团招聘",
        "search_url": "https://zhaopin.meituan.com/web/campus?city={city}",
        "list_selector": ".list-items .item",
        "title_selector": ".job-title, .position-title, h3 a",
        "location_selector": ".work-place, .location",
        "detail_url_selector": "a[href*=\"/job\"]",
        "base_url": "https://zhaopin.meituan.com",
    },
    "bytedance": {
        "name": "字节跳动招聘",
        "search_url": "https://jobs.bytedance.com/experienced/position?city={city}",
        "list_selector": ".position-list .position-item",
        "title_selector": ".position-title, .job-name",
        "location_selector": ".position-location, .city",
        "detail_url_selector": "a[href*=\"/position/\"]",
        "base_url": "https://jobs.bytedance.com",
    },
    "tencent": {
        "name": "腾讯招聘",
        "search_url": "https://careers.tencent.com/search.html?city={city}",
        "list_selector": ".recruit-list .recruit-item",
        "title_selector": ".recruit-title, .job-name",
        "location_selector": ".recruit-location, .location",
        "detail_url_selector": "a[href*=\"/position\"]",
        "base_url": "https://careers.tencent.com",
    },
    "alibaba": {
        "name": "阿里招聘",
        "search_url": "https://talent.alibaba.com/off-campus/position-list?city={city}",
        "list_selector": ".position-list .position-item, .job-card",
        "title_selector": ".position-name, .job-title",
        "location_selector": ".location, .city-name",
        "detail_url_selector": "a",
        "base_url": "https://talent.alibaba.com",
    },
}

# 城市英文名映射（网站 URL 常用）
CITY_EN = {
    "成都": "chengdu",
    "北京": "beijing",
    "上海": "shanghai",
    "深圳": "shenzhen",
    "广州": "guangzhou",
    "杭州": "hangzhou",
}


class CompanySiteCollector(BaseCollector):
    """企业官网招聘页采集器。"""

    def __init__(self, output_dir: Path, site_name: str = "all"):
        self.site_name = site_name
        source_name = f"company_site_{site_name}"
        super().__init__(source_name, output_dir, rate_min=3.0, rate_max=8.0, timeout=20.0)

    def build_search_url(self, query: ScrapeQuery) -> str:
        """构造搜索 URL（使用主站点配置）。"""
        site_cfg = self._get_site_config()
        city_en = CITY_EN.get(query.city, query.city)
        return site_cfg["search_url"].replace("{city}", city_en)

    def parse_list_page(self, html: str, query: ScrapeQuery) -> list[RawJob]:
        """解析列表页 HTML。"""
        site_cfg = self._get_site_config()
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(site_cfg["list_selector"])
        if not items:
            # 回退：尝试通用 job 容器
            items = soup.select(".job-item, .position-card, [class*=\"job\"], [class*=\"position\"]")
        if not items:
            return []

        jobs: list[RawJob] = []
        for item in items:
            title_el = item.select_one(site_cfg["title_selector"])
            location_el = item.select_one(site_cfg["location_selector"])
            link_el = item.select_one(site_cfg["detail_url_selector"])

            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            raw_location = location_el.get_text(strip=True) if location_el else query.city
            detail_href = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                detail_href = href if href.startswith("http") else site_cfg["base_url"] + href

            jobs.append(RawJob(
                source=self.source_name,
                source_url=detail_href,
                raw_title=title,
                raw_company=site_cfg["name"].replace("招聘", ""),
                raw_location=raw_location,
                raw_description="",
                raw_skills=[],
            ))
        return jobs

    def is_blocked(self, html: str) -> bool:
        """检测是否被拦截。"""
        blocked_signals = ["访问受限", "请稍后再试", "403 Forbidden", "验证码", "captcha", "你的IP被限制"]
        lower = html.lower()
        return any(sig.lower() in lower for sig in blocked_signals)

    def _get_site_config(self) -> dict:
        """获取当前站点配置。"""
        if self.site_name == "all":
            return SITE_CONFIGS.get("meituan", list(SITE_CONFIGS.values())[0])
        return SITE_CONFIGS.get(self.site_name, list(SITE_CONFIGS.values())[0])

    @staticmethod
    def available_sites() -> list[str]:
        return list(SITE_CONFIGS.keys())
