"""前程无忧（51job）xbrowser 采集器。

通过 xbrowser 操纵真实 Chrome 浏览器，调用 51job SPA 的搜索 API
获取结构化岗位数据（JSON），无需解析 HTML。

API: https://we.51job.com/api/job/search-pc
城市代码: 020000=上海, 090200=成都, 010000=北京, 040000=深圳, 030200=广州
"""

from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import RawJob, ScrapeQuery
from ..anti_crawl import (
    build_human_behavior_js,
    city_interval_sleep,
    keyword_interval_sleep,
    page_interval_sleep,
    random_sleep,
    retry_on_failure,
)

logger = logging.getLogger("scraping.job51_xbrowser")


class WAFBlockError(Exception):
    """WAF 拦截异常 - 需要刷新会话而非重试。"""
    pass


class XBEvalError(Exception):
    """xbrowser eval 通信异常。"""
    pass


# ── 城市代码映射 ──────────────────────────────────────────

CITY_CODES: dict[str, str] = {
    "北京": "010000",
    "上海": "020000",
    "广州": "030200",
    "深圳": "040000",
    "杭州": "080200",
    "成都": "090200",
    "南京": "070200",
    "武汉": "180200",
    "西安": "200200",
    "重庆": "060000",
}

# ── xb.cjs 路径 ──────────────────────────────────────────

XB_BASE_DIR = os.path.expanduser(
    "~/Library/Application Support/QClaw/openclaw/config/skills/xbrowser"
)
XB_CJS = os.path.join(XB_BASE_DIR, "scripts", "xb.cjs")
NODE = os.environ.get("QCLAW_CLI_NODE_BINARY", "node")


class Job51XBrowserCollector:
    """通过 xbrowser 调用 51job 搜索 API 采集岗位数据。"""

    def __init__(
        self,
        output_dir: Path,
        *,
        page_size: int = 20,
        max_pages: int = 50,
        rate_min: float = 15.0,
        rate_max: float = 30.0,
        timeout: float = 30.0,
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.page_size = page_size
        self.max_pages = max_pages
        self.rate_min = rate_min
        self.rate_max = rate_max
        self.timeout = timeout
        self.results: list[RawJob] = []
        self._session_ready = False
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3
        self._waf_cooldown = 120  # WAF 冷却秒数

    # ── xbrowser 交互 ─────────────────────────────────────

    def _xb_eval(self, js_code: str, timeout_sec: int = 15) -> dict:
        """在浏览器中执行 JS 代码并返回结果。

        注意: js_code 不能包含单引号（shell 单引号传递）。
        """
        cmd = [
            NODE, XB_CJS, "run", "--browser", "default",
            "--timeout", str(timeout_sec),
            "eval", js_code,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec + 5,
        )
        if result.returncode != 0:
            logger.error("xb eval failed: %s", result.stderr[:300])
            raise RuntimeError(f"xb eval failed: {result.stderr[:200]}")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.error("xb eval JSON parse error, stdout: %s", result.stdout[:500])
            raise

        if not data.get("ok"):
            error = data.get("error", "unknown")
            hint = data.get("hint", "")
            logger.error("xb browser error: %s (hint: %s)", error, hint)
            raise RuntimeError(f"xb browser error: {error}")

        return data

    def _xb_open(self, url: str, retries: int = 3) -> None:
        """打开 URL 并等待加载，带重试。"""
        last_error = None
        for attempt in range(retries):
            if attempt > 0:
                wait = 2 ** attempt
                logger.info("xb open retry %d/%d after %ds", attempt, retries - 1, wait)
                time.sleep(wait)
            logger.info("xb open %s", url)
            cmd = [
                NODE, XB_CJS, "run", "--browser", "default",
                "--timeout", "25", "open", url,
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            except subprocess.TimeoutExpired:
                last_error = RuntimeError("xb open timed out")
                continue
            if result.returncode != 0:
                last_error = RuntimeError(f"xb open failed: {result.stderr[:200]}")
                continue

            data = json.loads(result.stdout)
            if not data.get("ok"):
                last_error = RuntimeError(f"xb open error: {data.get('error', 'unknown')}")
                continue
            return

        raise last_error or RuntimeError("xb open failed after retries")

    def _ensure_session(self, keyword: str, city_code: str) -> None:
        """确保浏览器会话已建立（打开搜索页建立 cookie/session）。
        浏览器刚重启时 SPA 初始化较慢，需要更长等待。"""
        if self._session_ready:
            return
        url = f"https://we.51job.com/pc/search?keyword={keyword}&location={city_code}"
        self._xb_open(url)
        # 浏览器重启后的首次连接需要更长初始化时间
        sleep = 5 if getattr(self, "_first_session", True) else 2
        time.sleep(sleep)
        self._first_session = False
        self._session_ready = True
        logger.info("session ready (sleep=%ds)", sleep)

    # ── API 调用 ──────────────────────────────────────────

    def _build_api_url(self, keyword: str, city_code: str, page: int) -> str:
        """构建 API URL。"""
        # 注意: 该 URL 会被注入到 JS 代码中，JS 使用模板字面量拼接
        params = (
            f"api_key=51job&"
            f"keyword={keyword}&searchType=2&"
            f"function=&industry=&"
            f"jobArea={city_code}&jobArea2=&"
            f"landmark=&metro=&"
            f"salary=&workYear=&degree=&"
            f"companyType=&companySize=&"
            f"jobType=&issueDate=&"
            f"sortType=0&"
            f"pageNum={page}&pageSize={self.page_size}&"
            f"requestId=&"
            f"source=1&accountId=&"
            f"pageCode=sou%7Csou%7Csoulb"
        )
        return params

    def _build_extract_js(self, keyword: str, city_code: str, page: int) -> str:
        """生成数据提取 JS 代码（使用同步 XHR，因为 xbrowser eval 不支持异步 fetch）。

        URL 在 Python 端完整构建后注入到 JS 代码中，
        避免 JS 字符串拼接出错。
        """
        api_url = (
            "https://we.51job.com/api/job/search-pc"
            f"?api_key=51job&timestamp=__TS__"
            f"&keyword={keyword}&searchType=2"
            f"&function=&industry="
            f"&jobArea={city_code}&jobArea2="
            f"&landmark=&metro="
            f"&salary=&workYear=&degree="
            f"&companyType=&companySize="
            f"&jobType=&issueDate="
            f"&sortType=0"
            f"&pageNum={page}&pageSize={self.page_size}"
            f"&requestId="
            f"&source=1&accountId="
            f"&pageCode=sou%7Csou%7Csoulb"
        )

        # 使用同步 XHR（不是 fetch）是因为 xbrowser 的 eval 不支持异步 Promise/fetch，
        # 但同步 XMLHttpRequest 可以正常工作（阻塞线程直到请求完成）。
        js = f"""(function() {{
  try {{
    var apiUrl = "{api_url}".replace("__TS__", Date.now());
    var xhr = new XMLHttpRequest();
    xhr.open("GET", apiUrl, false);
    xhr.send();
    if (xhr.status !== 200) return JSON.stringify({{error: "HTTP " + xhr.status}});
    var data = JSON.parse(xhr.responseText);
    if (data.status !== "1") return JSON.stringify({{error: data.message || "api error"}});
    var items = data.resultbody.job.items;
    var total = data.resultbody.job.totalCount || 0;
    var extracted = items.map(function(j) {{
      return {{
        id: j.jobId || "",
        title: j.jobName || "",
        company: j.fullCompanyName || j.companyName || "",
        salary: j.provideSalaryString || "",
        area: j.jobAreaString || "",
        exp: j.workYearString || "",
        edu: j.degreeString || "",
        industry: j.companyIndustryType1Str || "",
        coType: j.companyTypeString || "",
        coSize: j.companySizeString || "",
        desc: (j.jobDescribe || "").substring(0, 3000),
        tags: j.jobTags || [],
        welfare: (j.jobWelfareCodeDataList || []).map(function(w) {{ return w.welfareName || ""; }}).filter(Boolean),
        href: j.jobHref || "",
        date: j.issueDateString || "",
        updateDate: j.updateDateTime || "",
        lon: j.lon || "",
        lat: j.lat || "",
        term: j.termStr || "",
        remote: !!j.isRemoteWork,
        intern: !!j.isIntern,
        salaryMin: j.jobSalaryMin || "",
        salaryMax: j.jobSalaryMax || ""
      }};
    }});
    return JSON.stringify({{total: total, page: {page}, count: extracted.length, items: extracted}});
  }} catch(e) {{
    return JSON.stringify({{error: "JS: " + e.message}});
  }}
}})()"""
        return js

    # ── WAF 检测与恢复 ───────────────────────────────────

    def _detect_waf(self, data: dict) -> bool:
        """检测 API 响应是否被 WAF 拦截。"""
        error = data.get("error", "")
        if not error:
            return False
        waf_keywords = ["aliyun", "challenge", "captcha", "blocked", "verify", "WAF", "安全"]
        return any(kw.lower() in error.lower() for kw in waf_keywords)

    def _reload_and_wait(self, url: str) -> None:
        """重新加载页面并等待冷却。"""
        logger.info("WAF detected, reloading page and cooling down %.0fs...", self._waf_cooldown)
        self._session_ready = False
        try:
            self._xb_open(url)
            # 模拟人类行为
            human_js = build_human_behavior_js()
            try:
                self._xb_eval(human_js, timeout_sec=5)
            except Exception:
                pass
            self._session_ready = True
        except Exception as e:
            logger.warning("reload failed: %s", e)
        wait = self._waf_cooldown + random.uniform(0, 30)
        logger.info("cooling down %.1fs...", wait)
        time.sleep(wait)
        self._consecutive_errors = 0

    # ── 核心采集逻辑 ──────────────────────────────────────

    def fetch_page(
        self, keyword: str, city_code: str, page: int
    ) -> tuple[int, list[dict]]:
        """获取单页数据。返回 (total_count, items)。不自动重试——由调用方处理。"""
        self._ensure_session(keyword, city_code)

        js = self._build_extract_js(keyword, city_code, page)
        logger.info("fetching keyword=%s city=%s page=%d", keyword, city_code, page)

        try:
            result = self._xb_eval(js, timeout_sec=self.timeout)
        except Exception as e:
            raise XBEvalError(f"xb_eval failed: {e}") from e

        # xb.cjs 返回: {ok, data: {browser_command, result: {success, data: {origin, result}}}}
        eval_result = result.get("data", {}).get("result", {}).get("data", {}).get("result", "{}")

        # xb.cjs 有时会预解析 JSON 返回值为 dict
        if isinstance(eval_result, dict):
            data = eval_result
        elif isinstance(eval_result, str):
            # 检测 WAF HTML 响应（返回的不是 JSON 而是 HTML 挑战页）
            stripped = eval_result.strip()
            if stripped.startswith(("<", "<!")):
                logger.warning("WAF HTML detected, len=%d: %s", len(stripped), stripped[:200])
                raise WAFBlockError(f"WAF returned HTML (len={len(stripped)})")
            try:
                data = json.loads(eval_result)
            except json.JSONDecodeError:
                logger.error("JSON parse error for page %d: %s", page, eval_result[:300])
                raise
        else:
            raise TypeError(f"unexpected eval result type: {type(eval_result)}")

        if "error" in data:
            err_msg = data["error"]
            logger.error("API error for page %d: %s", page, err_msg)
            # 检查是否是 WAF 相关错误
            if any(kw in str(err_msg).lower() for kw in ["html", "challenge", "blocked", "forbidden", "unexpected"]):
                raise WAFBlockError(f"API WAF error: {err_msg}")
            raise RuntimeError(f"API error: {err_msg}")

        total = data.get("total", 0)
        items = data.get("items", [])

        # 检测 WAF 无声拒绝：返回 total=0 但页面正常（非 404）
        if total == 0 and not items:
            self._consecutive_errors += 1
            logger.warning("page %d: empty result (total=0), consecutive_errors=%d", page, self._consecutive_errors)
            if self._consecutive_errors >= 2:
                raise WAFBlockError(f"WAF silent block: {self._consecutive_errors} empty results in a row")
        else:
            # 成功时重置错误计数（在 collect 中）
            pass

        logger.info("page %d: got %d items (total=%d)", page, len(items), total)
        return total, items

    def _to_raw_job(self, item: dict, keyword: str, city: str) -> RawJob:
        """将 API item 转换为 RawJob dataclass。"""
        return RawJob(
            source="job51",
            source_job_id=f"job51-{item.get('id', '')}",
            source_url=item.get("href", ""),
            source_platform_status="ok",
            raw_title=item.get("title", ""),
            raw_company=item.get("company", ""),
            raw_salary=item.get("salary", ""),
            raw_location=item.get("area", ""),
            raw_experience=item.get("exp", ""),
            raw_education=item.get("edu", ""),
            raw_industry=item.get("industry", ""),
            raw_company_size=item.get("coSize", ""),
            raw_financing="",
            raw_skills=item.get("tags", []),
            raw_description=item.get("desc", ""),
            raw_publish_time=item.get("date", ""),
            query={"city": city, "keyword": keyword},
            crawl_time=datetime.now().replace(microsecond=0).isoformat(sep=" "),
        )

    def collect(
        self,
        city: str,
        keywords: list[str],
        *,
        max_pages_per_keyword: int = 5,
        max_jobs_total: int = 200,
        reset_progress: bool = False,
    ) -> list[RawJob]:
        """执行采集。简单策略：每页尝试一次，失败跳过当前关键词。"""
        city_code = CITY_CODES.get(city)
        if not city_code:
            raise ValueError(f"Unknown city: {city}. Available: {list(CITY_CODES.keys())}")

        self.results = []
        total_queries = 0
        self._consecutive_errors = 0

        logger.info("=== job51_xbrowser collect: city=%s code=%s keywords=%s ===",
                     city, city_code, keywords)

        for kw_idx, keyword in enumerate(keywords):
            if len(self.results) >= max_jobs_total:
                break
            if reset_progress:
                self._clear_kw_progress(city, keyword)

            logger.info("--- keyword=%s (%d/%d) ---", keyword, kw_idx + 1, len(keywords))

            try:
                total_count, items = self.fetch_page(keyword, city_code, page=1)
                total_queries += 1
            except Exception as e:
                logger.warning("keyword=%s page=1 failed: %s", keyword, e)
                self._consecutive_errors += 1
                if self._consecutive_errors >= 3:
                    logger.warning("%d consecutive errors, reloading...", self._consecutive_errors)
                    self._reload_and_wait(
                        f"https://we.51job.com/pc/search?keyword={keyword}&location={city_code}"
                    )
                    self._consecutive_errors = 0
                continue

            if not items:
                logger.warning("keyword=%s page=1 empty (total=%d), skipping", keyword, total_count)
                self._consecutive_errors += 1
                continue

            self._consecutive_errors = 0

            # 加第一页数据
            jobs = [self._to_raw_job(item, keyword, city) for item in items]
            self.results.extend(jobs)
            logger.info("  page 1: %d items (total=%d)", len(items), total_count)

            # 计算需要多少页
            actual_max = min(max_pages_per_keyword, self.max_pages, (total_count // self.page_size) + 1)
            logger.info("  will fetch %d pages", actual_max)

            for page in range(2, actual_max + 1):
                if len(self.results) >= max_jobs_total:
                    break

                # 页间限速
                page_interval_sleep(page, self.rate_min, self.rate_max)

                try:
                    _, items = self.fetch_page(keyword, city_code, page)
                    total_queries += 1
                except Exception as e:
                    logger.warning("keyword=%s page=%d failed: %s", keyword, page, e)
                    break  # 失败就停，跳到下一个关键词

                if not items:
                    logger.info("  page %d: empty, stopping", page)
                    break

                new_jobs = [self._to_raw_job(item, keyword, city) for item in items]
                self.results.extend(new_jobs)
                logger.info("  page %d: %d items (cumulative=%d)", page, len(new_jobs), len(self.results))

            # 关键词间随机等待
            if kw_idx < len(keywords) - 1:
                kw_wait = keyword_interval_sleep()
                logger.info("keyword=%s done, waiting %.1fs", keyword, kw_wait)

        logger.info("=== job51_xbrowser done: %d jobs, %d queries ===",
                     len(self.results), total_queries)
        return self.results

    # ── 断点续传进度管理 ──────────────────────────────────

    def _progress_dir(self) -> Path:
        p = self.output_dir / "progress"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _progress_file(self, city: str, keyword: str) -> Path:
        safe_kw = keyword.replace("/", "_").replace(" ", "_")
        return self._progress_dir() / f"{city}_{safe_kw}.json"

    def _load_kw_progress(self, city: str, keyword: str) -> tuple[int, int]:
        """读取进度，返回 (last_page, total_collected)。"""
        pf = self._progress_file(city, keyword)
        if pf.exists():
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                return data.get("last_page", 0), data.get("total_collected", 0)
            except Exception:
                pass
        return 0, 0

    def _save_kw_progress(self, city: str, keyword: str, last_page: int, total_collected: int) -> None:
        """保存进度。"""
        pf = self._progress_file(city, keyword)
        pf.write_text(
            json.dumps({
                "last_page": last_page,
                "total_collected": total_collected,
                "updated_at": datetime.now().replace(microsecond=0).isoformat(sep=" "),
            }, ensure_ascii=False),
            encoding="utf-8",
        )

    def _clear_kw_progress(self, city: str, keyword: str) -> None:
        """清除断点进度。"""
        pf = self._progress_file(city, keyword)
        if pf.exists():
            pf.unlink()
            logger.info("progress cleared: %s - %s", city, keyword)

    def save_raw(self, prefix: str = "job51", jobs: Optional[list] = None) -> Path:
        """保存结果为 JSONL。支持通过 jobs 参数指定要保存的结果列表。"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_file = self.output_dir / date_str / f"{prefix}.jsonl"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        source_jobs = jobs if jobs is not None else self.results
        seen = set()
        written = 0
        with output_file.open("w", encoding="utf-8") as f:
            for job in source_jobs:
                # 去重
                key = f"{job.source_url}|{job.raw_title}|{job.raw_company}"
                if key in seen:
                    continue
                seen.add(key)

                record = asdict(job)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1

        logger.info("saved %d jobs (after dedup) -> %s", written, output_file)
        return output_file


def collect_job51_xbrowser(
    output_dir: Path,
    city: str = "成都",
    keywords: Optional[list[str]] = None,
    max_pages: int = 5,
    max_total: int = 200,
) -> Path:
    """便捷函数：一键采集 51job 成都岗位。"""
    if keywords is None:
        keywords = [
            "Python",
            "数据分析",
            "数据开发",
            "算法",
            "Java",
        ]

    collector = Job51XBrowserCollector(output_dir, max_pages=max_pages)
    collector.collect(
        city=city,
        keywords=keywords,
        max_pages_per_keyword=max_pages,
        max_jobs_total=max_total,
    )
    return collector.save_raw()
