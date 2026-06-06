"""采集器基类：限速、重试、日志、进度追踪、断点续跑。"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from .models import NormalizedJob, RawJob, ScrapeQuery

logger = logging.getLogger("scraping")


# ── 限速器 ──────────────────────────────────────────────

class RateLimiter:
    """请求限速器，带随机抖动。"""

    def __init__(self, min_interval_seconds: float = 5.0, max_interval_seconds: float = 15.0):
        self.min_interval = min_interval_seconds
        self.max_interval = max_interval_seconds
        self._last_request: float = 0.0

    def wait(self) -> float:
        """等待直到可以发起下一次请求，返回实际等待秒数。"""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            delay = self.min_interval - elapsed + random.uniform(0, self.max_interval - self.min_interval)
            time.sleep(delay)
        self._last_request = time.monotonic()
        return elapsed


# ── 重试策略 ──────────────────────────────────────────────

def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 10.0,
    backoff_factor: float = 2.0,
):
    """指数退避重试。遇到请求失败时自动重试，失败次数用完抛出异常。"""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (backoff_factor ** attempt)
                jitter = delay * random.uniform(0.0, 0.5)
                total_delay = delay + jitter
                logger.warning("retry %d/%d after %.1fs: %s", attempt + 1, max_retries, total_delay, e)
                time.sleep(total_delay)
    raise last_error  # type: ignore[misc]


# ── 文件工具 ──────────────────────────────────────────────

def hash_content(text: str) -> str:
    """生成内容的 SHA256 哈希，用于重复检测。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── 抽象采集器 ──────────────────────────────────────────

class BaseCollector(ABC):
    """采集器抽象基类。

    子类需要实现:
      - build_search_url(query)   构建搜索 URL
      - parse_list_page(html, query)    解析列表页 HTML → RawJob 列表
      - parse_detail_page(html, url)    解析详情页 HTML → 补充字段
      - is_blocked(html)         判断是否被反爬拦截
    """

    def __init__(
        self,
        source_name: str,
        output_dir: Path,
        *,
        rate_min: float = 5.0,
        rate_max: float = 15.0,
        timeout: float = 30.0,
    ):
        self.source_name = source_name
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limiter = RateLimiter(rate_min, rate_max)
        self.timeout = timeout
        self.results: list[RawJob] = []
        self._setup_logging()

    def _setup_logging(self) -> None:
        log_dir = Path("logs/scraping")
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_dir / f"{self.source_name}.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    # ── 抽象方法 ──────────────────────────────────────────

    @abstractmethod
    def build_search_url(self, query: ScrapeQuery) -> str:
        """根据查询参数构建搜索页 URL。"""
        ...

    @abstractmethod
    def parse_list_page(self, html: str, query: ScrapeQuery) -> list[RawJob]:
        """解析搜索列表页 HTML，返回 RawJob 列表。"""
        ...

    @abstractmethod
    def is_blocked(self, html: str) -> bool:
        """判断响应是否被反爬拦截（403/验证码/登录页）。"""
        ...

    def parse_detail_page(self, html: str, url: str) -> dict:
        """解析详情页 HTML，返回补充字段。默认不解析详情页。"""
        return {}

    # ── 通用采集逻辑 ──────────────────────────────────────

    def fetch_page(self, url: str) -> str:
        """获取页面 HTML，含限速和重试。"""
        def _do():
            self.rate_limiter.wait()
            logger.info("fetching %s", url)
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(
                    url,
                    headers={
                        "User-Agent": self._random_ua(),
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Accept-Encoding": "gzip, deflate",
                        "Connection": "keep-alive",
                    },
                )
                resp.raise_for_status()
                return resp.text
        return retry_with_backoff(_do, max_retries=3)

    def fetch_page_safe(self, url: str) -> tuple[str, str]:
        """获取页面，返回 (html, status)。不抛异常。"""
        try:
            html = self.fetch_page(url)
            if self.is_blocked(html):
                return html, "blocked"
            return html, "ok"
        except Exception as e:
            logger.error("fetch failed: %s → %s", url, e)
            return "", f"error: {e}"

    def enrich_with_detail(self, job: RawJob) -> bool:
        """用详情页补充字段。返回 False 表示跳过或失败。"""
        if not job.source_url:
            return False
        html, status = self.fetch_page_safe(job.source_url)
        if status != "ok":
            job.source_platform_status = status
            return False
        extra = self.parse_detail_page(html, job.source_url)
        if extra:
            for key, value in extra.items():
                if hasattr(job, key) and not getattr(job, key):
                    setattr(job, key, value)
        return True

    def collect(
        self,
        city: str,
        keywords: list[str],
        *,
        max_pages_per_keyword: int = 5,
        max_jobs_total: int = 200,
        enrich_detail: bool = False,
    ) -> list[RawJob]:
        """执行采集：对每个关键词逐页抓取。

        Args:
            city: 目标城市
            keywords: 搜索关键词列表
            max_pages_per_keyword: 每个关键词最多翻页数
            max_jobs_total: 总岗位上限
            enrich_detail: 是否访问详情页补充字段
        """
        self.results = []
        self._progress: set[str] = self._load_progress()
        query_count = 0

        logger.info("=== %s collect start: city=%s, keywords=%s ===", self.source_name, city, keywords)

        for keyword in keywords:
            if len(self.results) >= max_jobs_total:
                break
            consecutive_failures = 0
            for page in range(1, max_pages_per_keyword + 1):
                if len(self.results) >= max_jobs_total:
                    break

                query = ScrapeQuery(
                    source=self.source_name,
                    city=city,
                    keyword=keyword,
                    page=page,
                    fetched_at=datetime.now().replace(microsecond=0).isoformat(sep=" "),
                )
                query.search_url = self.build_search_url(query)

                # 断点续跑
                if query.task_key in self._progress:
                    logger.info("skip already done: %s", query.task_key)
                    continue

                query_count += 1
                html, status = self.fetch_page_safe(query.search_url)

                if status != "ok":
                    logger.warning("page status=%s: %s", status, query.search_url)
                    consecutive_failures += 1
                    self._progress.add(query.task_key)
                    self._save_progress()
                    if consecutive_failures >= 3:
                        logger.warning("too many failures for keyword=%s, stopping", keyword)
                        break
                    continue

                consecutive_failures = 0
                jobs = self.parse_list_page(html, query)
                logger.info("keyword=%s page=%d → %d jobs", keyword, page, len(jobs))

                if not jobs:
                    self._progress.add(query.task_key)
                    self._save_progress()
                    break  # 空结果，停止翻页

                for job in jobs:
                    job.query = {"city": city, "keyword": keyword, "page": page}
                    job.crawl_time = query.fetched_at
                    if enrich_detail:
                        self.enrich_with_detail(job)

                self.results.extend(jobs)
                self._progress.add(query.task_key)
                self._save_progress()

        logger.info("=== %s collect done: %d jobs, %d queries ===", self.source_name, len(self.results), query_count)
        self._clear_progress()
        return self.results

    def save_raw(self) -> Path:
        """将采集结果保存为 JSONL 文件。"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_file = self.output_dir / date_str / f"{self.source_name}.jsonl"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w", encoding="utf-8") as f:
            for job in self.results:
                record = {
                    "source": job.source,
                    "source_job_id": job.source_job_id,
                    "source_url": job.source_url,
                    "source_platform_status": job.source_platform_status,
                    "raw_title": job.raw_title,
                    "raw_company": job.raw_company,
                    "raw_salary": job.raw_salary,
                    "raw_location": job.raw_location,
                    "raw_experience": job.raw_experience,
                    "raw_education": job.raw_education,
                    "raw_industry": job.raw_industry,
                    "raw_company_size": job.raw_company_size,
                    "raw_financing": job.raw_financing,
                    "raw_skills": job.raw_skills,
                    "raw_description": job.raw_description,
                    "raw_publish_time": job.raw_publish_time,
                    "query": job.query,
                    "crawl_time": job.crawl_time,
                    "parser_version": job.parser_version,
                    "raw_hash": hash_content(json.dumps(job.raw_title + job.raw_company + job.source_url, ensure_ascii=False)),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info("saved %d raw jobs → %s", len(self.results), output_file)
        return output_file

    # ── 进度持久化 ──────────────────────────────────────────

    def _progress_file(self) -> Path:
        return self.output_dir / f".progress_{self.source_name}.json"

    def _load_progress(self) -> set[str]:
        pf = self._progress_file()
        if pf.exists():
            return set(json.loads(pf.read_text()))
        return set()

    def _save_progress(self) -> None:
        self._progress_file().write_text(json.dumps(sorted(self._progress)))

    def _clear_progress(self) -> None:
        pf = self._progress_file()
        if pf.exists():
            pf.unlink()

    @staticmethod
    def _random_ua() -> str:
        ua_list = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        ]
        return random.choice(ua_list)
