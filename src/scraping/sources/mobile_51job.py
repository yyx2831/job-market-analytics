"""
51job 移动站采集器 v3 — xbrowser 页面管理 + CDP 交互

流程：
  1. xbrowser (CFT) 打开 we.51job.com/m/search
  2. xb fill 搜索框 + CDP 点击搜索按钮
  3. CDP 滚动加载 → xb snapshot 提取 ARIA → Python 解析
  4. 直接写入 SQLite (data/processed/jobs.db)，匹配现有 schema

用 run_spider.py 调用: --source job51_mobile --keywords Python Java --limit-per-kw 30
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import websockets

logger = logging.getLogger(__name__)

XB_CJS = os.path.expanduser("~/.qclaw/skills/xbrowser/scripts/xb.cjs")
BROWSER = "cft"
TIMEOUT = "25000"
DEFAULT_DB = "data/processed/jobs.db"

KNOWN_CITIES = {
    "北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "南京",
    "西安", "重庆", "苏州", "天津", "长沙", "合肥", "东莞", "佛山",
    "惠州", "嘉兴", "昆山", "孝感", "岳阳", "乌鲁木齐", "淮安", "郑州",
    "济南", "青岛", "大连", "厦门", "福州", "无锡", "宁波", "珠海",
    "桂林", "南宁", "海口", "兰州", "银川", "西宁", "拉萨", "贵阳",
    "昆明", "太原", "石家庄", "呼和浩特", "沈阳", "长春", "哈尔滨",
}

_NON_JOB_TEXTS = {
    "职位搜索", "消息", "全国", "搜索", "区域", "职能", "综合排序", "筛选",
    "申请职位（0/20）", "申请职位", "登录查看更多职位", "距离优先",
    "设置地址", "最新优先", "薪资优先", "薪资范围", "确定",
    "为你推荐以下职位", "去申请", "立即登录", "没有找到匹配的职位",
}


# ── xbrowser 封装 ─────────────────────────────────────────────────

def xb_run(*args: str) -> dict:
    cmd = ["node", XB_CJS, "run", "--browser", BROWSER, "--timeout", TIMEOUT] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        logger.error("xb failed: %s", result.stderr[:200])
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.error("xb invalid JSON: %s", result.stdout[:200])
        return {}

def xb_batch(*commands: str) -> list[dict]:
    cmd = ["node", XB_CJS, "run", "--browser", BROWSER, "--timeout", TIMEOUT,
           "batch", "--bail"] + list(commands)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error("xb batch failed: %s", result.stderr[:200])
        return []
    try:
        data = json.loads(result.stdout)
        return data.get("data", {}).get("result", [])
    except json.JSONDecodeError:
        return []

def xb_snapshot(depth: int = 8, interactive: bool = False) -> dict:
    if interactive:
        data = xb_run("snapshot", "-i", "-c")
    else:
        data = xb_run("snapshot", "-d", str(depth))
    return data.get("data", {}).get("result", {}).get("data", {})

def xb_cleanup():
    subprocess.run(["node", XB_CJS, "cleanup"], capture_output=True, timeout=10)

def xb_get_cdp_url() -> str:
    data = xb_run("get", "cdp-url")
    return data.get("data", {}).get("result", {}).get("data", {}).get("cdpUrl", "")


# ── CDP 工具 ──────────────────────────────────────────────────────

class CdpClient:
    def __init__(self, ws_url: str):
        self._url = ws_url
        self._ws = None
        self._mid = 0

    async def __aenter__(self):
        self._ws = await websockets.connect(self._url, max_size=20 * 1024 * 1024)
        return self

    async def __aexit__(self, *args):
        if self._ws:
            await self._ws.close()

    async def call(self, method: str, params: dict = None, sid: str = None) -> dict:
        self._mid += 1
        msg = {"id": self._mid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await self._ws.send(json.dumps(msg))
        for _ in range(100):
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
                resp = json.loads(raw)
                if resp.get("id") == self._mid:
                    return resp
            except asyncio.TimeoutError:
                continue
        return {"error": "timeout"}

    async def evaluate(self, expression: str, sid: str) -> dict:
        return await self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True}, sid)

    async def get_51job_session(self) -> str:
        rt = await self.call("Target.getTargets")
        for t in rt.get("result", {}).get("targetInfos", []):
            if t["type"] == "page" and "51job" in t.get("url", ""):
                sess = await self.call("Target.attachToTarget", {
                    "targetId": t["targetId"], "flatten": True})
                sid = sess["result"]["sessionId"]
                await self.call("Page.enable", {}, sid)
                await self.call("Runtime.enable", {}, sid)
                return sid
        raise RuntimeError("No 51job target found")


# ── 数据模型 ───────────────────────────────────────────────────────

@dataclass
class ParsedJob:
    """标准化岗位数据（薪资统一为 元/月，匹配 DB schema）"""
    title: str = ""
    salary_text: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_unit: str = "month"
    experience: str = ""
    education: str = ""
    company: str = ""
    company_type: str = ""
    company_size: str = ""
    city: str = ""
    district: str = ""
    source: str = "job51"
    tags: list = field(default_factory=list)
    raw_segments: list = field(default_factory=list)

    SALARY_RE = re.compile(
        r"(?P<min>[\d.]+)\s*[-~至]\s*(?P<max>[\d.]+)\s*(?P<unit>千|万|元)"
        r"\s*(?:·\d+薪)?\s*[//]?\s*(?P<period>月|年)?"
    )
    SALARY_SINGLE_RE = re.compile(
        r"(?P<val>[\d.]+)\s*(?P<unit>千|万|元)\s*(?:以上|以下)?"
        r"\s*(?:·\d+薪)?\s*[//]?\s*(?P<period>月|年)?"
    )

    # ── 静态识别 ──
    @staticmethod
    def _is_salary(text: str) -> bool:
        return bool(re.search(r"[\d.]+\s*[-~]\s*[\d.]+\s*[千万]|[\d.]+\s*[千万元]", text))

    @staticmethod
    def _is_exp(text: str) -> bool:
        return bool(re.search(r"\d+[\s-]*年|应届|不限|经验", text))

    @staticmethod
    def _is_edu(text: str) -> bool:
        return text in {"本科", "硕士", "博士", "大专", "中技/中专", "高中", "初中", "学历不限"}

    @staticmethod
    def _is_company_type(text: str) -> bool:
        return bool(re.search(r"民营|国企|外资|合资|上市|创业|事业", text))

    @staticmethod
    def _is_role(text: str) -> bool:
        return bool(re.match(r"^·", text)) or bool(re.search(r"HR|人事|经理|主管|专员|招聘", text))

    @staticmethod
    def _is_ui_chrome(text: str) -> bool:
        return text in _NON_JOB_TEXTS or bool(re.search(r"^\d+/\d+", text))

    # ── 解析 ──
    def _parse_salary(self, text: str) -> None:
        self.salary_text = text
        m = self.SALARY_RE.search(text)
        if m:
            self.salary_min = float(m.group("min"))
            self.salary_max = float(m.group("max"))
            self._normalize(m.group("unit"), m.group("period") or "月")
            return
        m = self.SALARY_SINGLE_RE.search(text)
        if m:
            val = float(m.group("val"))
            self.salary_min = self.salary_max = val
            self._normalize(m.group("unit"), m.group("period") or "月")

    def _normalize(self, unit: str, period: str) -> None:
        """统一为 元/月，匹配数据库现有格式"""
        if self.salary_min is None:
            return
        mult = 10000.0 if unit == "万" else (1.0 if unit == "元" else 1000.0)
        if period == "年":
            mult /= 12.0
        self.salary_min = round(self.salary_min * mult, 0)
        if self.salary_max is not None:
            self.salary_max = round(self.salary_max * mult, 0)

    def _parse_location(self, text: str) -> None:
        parts = text.split("·")
        if len(parts) == 2 and parts[0].strip() in KNOWN_CITIES:
            self.city = parts[0].strip()
            self.district = parts[1].strip()
        elif text in KNOWN_CITIES:
            self.city = text
        elif len(text) <= 15:
            for c in sorted(KNOWN_CITIES, key=len, reverse=True):
                if text.startswith(c):
                    self.city = c
                    self.district = text[len(c):].lstrip("·")
                    return
            if not self._is_ui_chrome(text):
                self.city = text.strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw_segments", None)
        return d


_TAG_SET = {
    "五险一金", "年终奖金", "培训", "计算机", "金融行业", "项目管理",
    "办公软件", "cad", "年终奖", "绩效奖金", "餐补", "通讯补贴",
    "补充公积金", "周末双休", "带薪年假", "加班补助", "交通补助",
    "做五休二", "弹性工作", "专业培训", "节日福利", "定期体检",
}

_SKILL_KEYWORDS_LOWER = {
    "mysql", "linux", "sql", "redis", "python", "java", "docker",
    "kubernetes", "k8s", "git", "aws", "azure", "nginx", "tomcat",
    "mongodb", "postgresql", "oracle", "golang", "go", "c++", "c#",
    "php", "ruby", "scala", "html", "css", "css3", "html5",
    "javascript", "js", "node.js", "nodejs", "react", "vue", "vue.js",
    "angular", "hadoop", "hive", "spark", "flink", "kafka", "rabbitmq",
    "elasticsearch", "es", "tensorflow", "pytorch", "hibernate",
    "spring", "springboot", "mybatis", "django", "flask", "fastapi",
    "celery", "jenkins", "ansible", "terraform", "shell", "perl",
    "matlab", "r", "sas", "powerbi", "tableau", "excel", "ppt",
    "c", "rust", "swift", "kotlin", "typescript", "ts", "ai",
}


# ── ARIA 解析器 ────────────────────────────────────────────────────

def parse_snapshot(snapshot: str) -> list[ParsedJob]:
    """状态机解析 xbrowser ARIA snapshot → 岗位列表"""
    lines = snapshot.split("\n")
    jobs = []
    current = None
    state = "out"

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        is_static = stripped.startswith("- StaticText ")
        is_strong = stripped.startswith("- strong")
        is_emphasis = stripped.startswith("- emphasis")

        text = ""
        if is_static:
            m = re.match(r'^- StaticText\s+"(.+)"$', stripped)
            if m:
                text = m.group(1)

        if is_strong:
            if current and current.title and not ParsedJob._is_ui_chrome(current.title):
                jobs.append(current)
            current = ParsedJob()
            state = "in_strong"
            continue

        if current is None:
            continue

        if state == "in_strong":
            if is_static:
                if ParsedJob._is_ui_chrome(text):
                    current = None
                else:
                    current.title = text
                    state = "expect_salary"
            continue

        if is_emphasis:
            state = "in_emphasis"
            continue

        if state == "in_emphasis":
            if is_static:
                m = re.match(r"\s*(?P<type>.+?)\s+(?P<size>\d+人以上|少于\d+人|\d+-\d+人)?", text)
                if m:
                    current.company_type = (m.group("type") or "").strip()
                    current.company_size = (m.group("size") or "").strip()
                state = "expect_contact"
            continue

        if not is_static:
            if state in ("expect_salary", "in_tags"):
                state = "in_tags"
            continue

        if ParsedJob._is_ui_chrome(text):
            continue

        current.raw_segments.append(text)

        if state == "expect_salary":
            if ParsedJob._is_salary(text):
                current._parse_salary(text)
                state = "in_tags"
            continue

        if state == "in_tags":
            if ParsedJob._is_exp(text):
                current.experience = text
            elif ParsedJob._is_edu(text):
                current.education = text
            elif text.lower() in _SKILL_KEYWORDS_LOWER or text in _TAG_SET:
                current.tags.append(text)
            else:
                current.company = text
                state = "expect_company_type"
            continue

        if state == "expect_company_type":
            if ParsedJob._is_company_type(text):
                m = re.match(r"\s*(?P<type>.+?)\s+(?P<size>\d+人以上|少于\d+人|\d+-\d+人)?", text)
                if m:
                    current.company_type = (m.group("type") or "").strip()
                    current.company_size = (m.group("size") or "").strip()
                state = "expect_contact"
            elif not current.company:
                current.company = text
            continue

        if state == "expect_contact":
            if ParsedJob._is_role(text):
                pass
            else:
                current._parse_location(text)

    if current and current.title and not ParsedJob._is_ui_chrome(current.title):
        jobs.append(current)
    return jobs


# ── 采集核心 ───────────────────────────────────────────────────────

async def _search_and_scroll_cdp(keyword: str, cdp_url: str, scrolls: int = 4) -> None:
    """CDP: 搜索 + 滚动"""
    async with CdpClient(cdp_url) as cdp:
        sid = await cdp.get_51job_session()

        await cdp.evaluate(f"""
            (function() {{
                var inp = document.querySelector('input[placeholder*="职位"]');
                if (inp) {{
                    inp.value = '{keyword}';
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                }}
            }})()
        """, sid)
        await asyncio.sleep(0.5)

        await cdp.evaluate("""
            (function() {
                var all = document.querySelectorAll('*');
                for (var e of all) {
                    if (e.textContent.trim() === '搜索' && e.className === 'search_btn') {
                        e.click(); return 'clicked';
                    }
                }
                return 'not_found';
            })()
        """, sid)
        await asyncio.sleep(3)

        for i in range(scrolls):
            await cdp.evaluate(f"window.scrollBy(0, {600 + i * 200})", sid)
            await asyncio.sleep(1.0)
        await cdp.evaluate("window.scrollTo(0, document.body.scrollHeight)", sid)
        await asyncio.sleep(1.5)
        logger.debug("CDP: searched '%s' + scrolled %dx", keyword, scrolls)


def collect(keyword: str, city: str = "", limit: int = 50) -> list[ParsedJob]:
    """
    采集 51job 移动站岗位。

    Args:
        keyword: 搜索关键词
        city: 预留，移动站暂不支持区域筛选
        limit: 最多采集条数

    Raises:
        RuntimeError: xbrowser 不可用或 CDP 连接失败
        ValueError: 无搜索结果
    """
    try:
        xb_cleanup()
    except Exception as e:
        logger.warning("xb_cleanup 异常: %s", e)

    try:
        xb_batch(
            "open https://we.51job.com/m/search",
            "wait --load networkidle",
        )
    except Exception as e:
        raise RuntimeError(f"xbrowser 打开页面失败: {e}") from e

    logger.debug("Page opened")

    snap = xb_snapshot(depth=4, interactive=True)
    if not snap:
        raise RuntimeError("xbrowser snapshot 返回空 — 浏览器可能崩溃")
    refs = snap.get("refs", {})
    search_ref = next((r for r, i in refs.items() if i.get("role") == "textbox"), None)
    if search_ref:
        try:
            xb_batch(f"fill {search_ref} {keyword}")
        except Exception as e:
            logger.warning("fill 搜索框失败: %s, 尝试继续...", e)

    cdp_url = xb_get_cdp_url()
    if not cdp_url:
        raise RuntimeError("无法获取 CDP URL — xbrowser 可能未启动或 51job 页面未加载")

    scrolls = max(1, min(8, limit // 10))
    try:
        asyncio.run(_search_and_scroll_cdp(keyword, cdp_url, scrolls=scrolls))
    except Exception as e:
        raise RuntimeError(f"CDP 搜索/滚动失败: {e}") from e

    snap = xb_snapshot(depth=8)
    if not snap:
        raise RuntimeError("搜索结果 snapshot 为空")
    snapshot = snap.get("snapshot", "")
    if not snapshot:
        raise ValueError(f"关键词 '{keyword}' 无搜索结果 — 页面可能被拦截")

    jobs = parse_snapshot(snapshot)
    if not jobs:
        logger.warning("关键词 '%s' 解析到 0 条岗位 — 页面结构可能变化", keyword)

    logger.info("Collected %d jobs for '%s'", len(jobs), keyword)
    return jobs[:limit]


def save_to_db(jobs: list[ParsedJob], db_path: str = None) -> int:
    """写入 SQLite，匹配现有 jobs 表 schema"""
    import sqlite3

    db_path = db_path or DEFAULT_DB
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    count = 0
    now = datetime.now().isoformat(sep=" ", timespec="seconds")

    for j in jobs:
        if not j.title:
            continue
        try:
            industry_val = (j.company_type or "").replace(" ", "")
            skills_val = ",".join(j.tags) if j.tags else ""
            sal_avg = None
            if j.salary_min is not None and j.salary_max is not None:
                sal_avg = round((j.salary_min + j.salary_max) / 2, 0)
            elif j.salary_min is not None:
                sal_avg = j.salary_min

            dedupe = hashlib.md5(f"{j.title}|{j.company}|{j.city}".encode()).hexdigest()[:12]
            source_job_id = f"m51-{dedupe}"
            dedupe_key = f"job51|{source_job_id}"

            cur.execute(
                """INSERT OR IGNORE INTO jobs
                   (title, source, source_job_id, dedupe_key, company_name, city, district,
                    salary_text, salary_min, salary_max, salary_avg, salary_unit, salary_months,
                    experience, education, industry, company_size, skills, description,
                    publish_time, crawl_time, created_at, updated_at, is_active)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,12,?,?,?,?,?,?,?,?,?,?,1)""",
                (j.title, j.source, source_job_id, dedupe_key,
                 j.company, j.city, j.district,
                 j.salary_text, j.salary_min, j.salary_max, sal_avg, j.salary_unit,
                 j.experience, j.education, industry_val, j.company_size, skills_val,
                 f"mobile_51job | {j.company_type}" if j.company_type else "mobile_51job",
                 now, now, now, now)
            )
            count += 1
        except Exception as e:
            logger.warning("DB skip %s: %s", j.title[:20], e)
    conn.commit()
    conn.close()
    logger.info("DB: %d 条新增到 %s", count, db_path)
    return count


# ── CLI ────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="51job 移动站采集器")
    parser.add_argument("--keyword", default="Python")
    parser.add_argument("--city", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", help="JSON 输出")
    parser.add_argument("--db", help="SQLite 数据库路径")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    jobs = collect(args.keyword, args.city, args.limit)
    print(f"\n{'='*70}")
    print(f"  {args.keyword}: {len(jobs)} 条采集完成")
    print(f"{'='*70}")
    if jobs:
        for j in jobs:
            sal = f"¥{j.salary_min}-{j.salary_max}" if j.salary_min else "-"
            loc = f"{j.city}·{j.district}" if j.district else j.city or "?"
            print(f"  {j.title[:28]:30s} {sal:12s} {j.experience[:6]:8s} "
                  f"{j.education:6s} {loc:14s} {j.company_type:8s} {j.company[:20]}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump([j.to_dict() for j in jobs], f, ensure_ascii=False, indent=2)
        print(f"\n→ JSON: {args.output}")

    if args.db:
        n = save_to_db(jobs, args.db)
        print(f"→ DB: {args.db} ({n} 条新增)")


if __name__ == "__main__":
    main()
