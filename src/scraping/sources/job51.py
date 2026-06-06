"""前程无忧（51job）采集器。

从 51job 搜索页提取岗位信息。优先解析列表页已有字段，
详情页作为可选的增强步骤。
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

from ..base import BaseCollector
from ..models import RawJob, ScrapeQuery

logger = logging.getLogger("scraping.job51")


CITY_CODES = {
    "成都": "090200",
    "北京": "010000",
    "上海": "020000",
    "深圳": "040000",
    "广州": "030200",
    "杭州": "080200",
    "南京": "070200",
    "武汉": "180200",
    "西安": "200200",
    "重庆": "060000",
}


class Job51Collector(BaseCollector):
    """前程无忧搜索采集器。"""

    def __init__(self, output_dir: Path):
        super().__init__("job51", output_dir, rate_min=6.0, rate_max=15.0, timeout=25.0)

    def build_search_url(self, query: ScrapeQuery) -> str:
        area = CITY_CODES.get(query.city, "000000")
        keyword_encoded = urllib.parse.quote(query.keyword)
        return (
            f"https://search.51job.com/list/{area},000000,0000,00,9,99,"
            f"{keyword_encoded},2,{query.page}.html"
        )

    def parse_list_page(self, html: str, query: ScrapeQuery) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[RawJob] = []

        items = soup.select("div.el, div.joblist-item, div[class*=\"joblist\"]")
        if not items:
            return self._parse_json_data(soup, query)

        for idx, item in enumerate(items):
            try:
                job = self._parse_item(item, idx, query)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug("parse item error: %s", e)
                continue

        return jobs

    def _parse_item(self, item, index: int, query: ScrapeQuery) -> RawJob | None:
        title_el = item.select_one(".t1 span a, .job-name a, a[href*=\"/job/\"], a[href*=\"/jobs/\"]")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None

        source_url = ""
        source_job_id = ""
        if title_el and title_el.get("href"):
            href = title_el["href"]
            source_url = href if href.startswith("http") else f"https://jobs.51job.com{href}"
            id_match = re.search(r'/job/(\d+)', source_url) or re.search(r'/(\d+)\.html', source_url)
            if id_match:
                source_job_id = f"job51-{id_match.group(1)}"

        company_el = item.select_one(".t2 a, .company-name a, .cname")
        company = company_el.get_text(strip=True) if company_el else ""

        salary_el = item.select_one(".t3, .salary, .sal")
        salary = salary_el.get_text(strip=True) if salary_el else ""

        location_el = item.select_one(".t4, .location, .work-location")
        raw_location = location_el.get_text(strip=True) if location_el else query.city

        info_el = item.select_one(".t5, .job-info, .info")
        info_text = info_el.get_text(strip=True) if info_el else ""

        experience, education = self._parse_exp_edu(info_text)

        time_el = item.select_one(".t6, .time, .date")
        publish_time = time_el.get_text(strip=True) if time_el else ""

        return RawJob(
            source="job51",
            source_job_id=source_job_id,
            source_url=source_url,
            source_platform_status="ok",
            raw_title=title,
            raw_company=company,
            raw_salary=salary,
            raw_location=self._enrich_location(raw_location, query.city),
            raw_experience=experience,
            raw_education=education,
            raw_description="",
            raw_skills=[],
            raw_publish_time=publish_time,
        )

    def _parse_json_data(self, soup, query: ScrapeQuery) -> list[RawJob]:
        """尝试从内嵌 JSON 中提取数据。"""
        jobs: list[RawJob] = []
        scripts = soup.find_all("script")
        for script in scripts:
            text = script.string or ""
            if "engine_search_result" in text:
                json_match = re.search(r'"engine_search_result"\s*:\s*(\[.+?\])', text, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        for item in data:
                            attr = item.get("attribute_text", [])
                            jobs.append(RawJob(
                                source="job51",
                                source_job_id=f"job51-{item.get('jobid', '')}",
                                source_url=item.get("job_href", ""),
                                raw_title=item.get("job_name", ""),
                                raw_company=item.get("company_name", ""),
                                raw_salary=item.get("providesalary_text", ""),
                                raw_location=f"{query.city}\u00b7{item.get('workarea_text', '')}",
                                raw_experience=attr[0] if len(attr) > 0 else "",
                                raw_education=attr[1] if len(attr) > 1 else "",
                                raw_publish_time=item.get("issuedate", ""),
                            ))
                        if jobs:
                            return jobs
                    except (json.JSONDecodeError, KeyError):
                        pass
        return jobs

    def parse_detail_page(self, html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        extra: dict = {}

        desc_el = soup.select_one(".bmsg.job_msg, .job-detail, .job_msg, .job-description")
        if desc_el:
            extra["raw_description"] = desc_el.get_text(separator="\n", strip=True)[:5000]

        company_info_el = soup.select_one(".tmsg, .company-msg, .company-info")
        if company_info_el:
            info_text = company_info_el.get_text(strip=True)

            size_match = re.search(r'(规模|公司规模|人数)[：:]\s*(.{1,30})', info_text)
            if size_match:
                extra["raw_company_size"] = size_match.group(2).strip()

            industry_match = re.search(r'(行业|所属行业)[：:]\s*(.{1,50})', info_text)
            if industry_match:
                extra["raw_industry"] = industry_match.group(2).strip()

            finance_match = re.search(r'(融资|融资阶段|发展阶段)[：:]\s*(.{1,30})', info_text)
            if finance_match:
                extra["raw_financing"] = finance_match.group(2).strip()

        if extra.get("raw_description"):
            extra["raw_skills"] = self._extract_skills_from_text(extra["raw_description"])

        return extra

    _SKILL_PATTERNS = [
        "Python", "Java", "Go", r"C\+\+", "JavaScript", "TypeScript",
        "React", "Vue", r"Node\.?js", "Spring", "Django", "FastAPI", "Flask",
        "MySQL", "PostgreSQL", "Redis", "MongoDB", "Docker", "Kubernetes",
        "Linux", "SQL", "Excel", "Tableau", r"Power\s*BI",
        "机器学习", "深度学习", "数据分析", "数据可视化",
        "Figma", "Photoshop",
    ]

    def _extract_skills_from_text(self, text: str) -> list[str]:
        found = []
        for skill in self._SKILL_PATTERNS:
            if re.search(r'\b' + skill + r'\b', text, re.IGNORECASE):
                m = re.search(r'\b' + skill + r'\b', text)
                found.append(m.group(0) if m else skill)
        return sorted(set(found), key=found.index)

    def is_blocked(self, html: str) -> bool:
        if not html:
            return True
        lower = html.lower()
        signals = [
            "访问受限", "请稍后再试", "403 forbidden",
            "验证码", "captcha", "你的ip被限制",
            "系统繁忙", "访问过于频繁",
            "安全验证", "请滑动验证",
        ]
        if any(sig in lower for sig in signals):
            return True
        if "passport.51job.com" in lower or "login.51job.com" in lower:
            return True
        return False

    @staticmethod
    def _parse_exp_edu(info_text: str) -> tuple[str, str]:
        experience = ""
        education = ""
        exp_patterns = [
            r'(在校生/应届生)', r'(经验不限|无需经验)',
            r'(\d+[-~]\d+年)', r'(\d+年以上)',
        ]
        for pat in exp_patterns:
            m = re.search(pat, info_text)
            if m:
                experience = m.group(1)
                break
        edu_patterns = [
            r'(学历不限)', r'(高中)', r'(中专|中技)',
            r'(大专)', r'(本科)', r'(硕士)', r'(博士)',
        ]
        for pat in edu_patterns:
            m = re.search(pat, info_text)
            if m:
                education = m.group(1)
                break
        if not experience:
            for kw in ["应届", "毕业生", "经验不限", "1-3年", "3-5年", "5-10年"]:
                if kw in info_text:
                    experience = kw
                    break
        if not education:
            for kw in ["本科", "大专", "硕士", "博士", "不限"]:
                if kw in info_text:
                    education = kw
                    break
        return experience, education

    @staticmethod
    def _enrich_location(raw_location: str, city: str) -> str:
        if not raw_location:
            return city
        if city in raw_location:
            return raw_location
        return f"{city}\u00b7{raw_location}"
