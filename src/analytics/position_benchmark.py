"""
岗位对标分析器 — 跨城市/公司/技能维度的市场定位分析。

核心功能：
  1. 岗位名称标准化 → 聚类为职位簇
  2. 跨城市薪资对标 (P25/P50/P75)
  3. 同一职位的公司间薪资比较
  4. 个人薪资 vs 市场定位

用法：
  from src.analytics.position_benchmark import PositionBenchmark
  bm = PositionBenchmark(db_path="data/processed/jobs.db")
  
  # 对标分析
  result = bm.benchmark(title="Python开发", salary=15000, city="成都")
  # -> {percentile: 62.3, market_median: 13200, delta: +13.6%, ...}
  
  # 跨城市热力
  heatmap = bm.city_heatmap(title="Java开发")
  # -> {"北京": {"p50": 25000, "count": 320}, "上海": {...}, ...}
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# ── 职位名称标准化 ───────────────────────────────────────────────

# 公司/地点后缀 → 去除
_TITLE_STRIP_RE = re.compile(
    r"[-—–·•()（）](北京|上海|广州|深圳|成都|杭州|武汉|南京|西安|重庆|苏州|"
    r"双休|五险|六险|年假|年终|周末|外派|驻场|远程|外包|"
    r"国企|央企|上市|外资|创业|\d+薪|"
    r"J\d+|MJ\d+|DS\d+|社招|校招|实习|"
    r"(?:初中|高中|大专|本科|硕士|博士|不限)(?:及以上|及以上学历)?|"
    r"[\u4e00-\u9fff]{0,4}(?:方向|场景|领域)|"
    r"[\d.]+K|[\d.]+万|[\d.]+\s*[万元/年薪月]+)"
    r"(?:[-—–·•()（）].*?)?$",
    re.UNICODE,
)

# 职位层级关键词 → 标准化
_LEVEL_PREFIX_MAP = [
    (re.compile(r"^(高级|资深|Senior)\s*", re.UNICODE), "senior"),
    (re.compile(r"^(初级|Junior)\s*", re.UNICODE), "junior"),
    (re.compile(r"^(总监|负责人|总监级别|head\s*of)\s*", re.UNICODE), "lead"),
    (re.compile(r"^(经理|Manager)\s*", re.UNICODE), "manager"),
]

# 职位类别关键词归类
_FAMILY_MAP = [
    # AI/ML
    (re.compile(r"AI|算法|大模型|机器学习|深度学习|NLP|自然语言|计算机视觉|"
                r"Agent|智能体|人工智能|强化学习|数据科学", re.UNICODE), "AI/算法"),
    # 后端
    (re.compile(r"Java|Python|Go\s*Lang|Golang|PHP|C#|\.NET|后端|"
                r"服务端|Server|全栈|Node\s*\.?js", re.UNICODE), "后端开发"),
    # 前端
    (re.compile(r"前端|Web|H5|小程序|Vue|React|Angular|JavaScript|"
                r"UI\s*(?:设计|开发)?", re.UNICODE), "前端开发"),
    # 数据
    (re.compile(r"数据(?:分析|挖掘|仓库|开发|治理|建模|管理|科学|运营|"
                r"工程)|ETL|BI|报表|大数据|ETL", re.UNICODE), "数据"),
    # 测试
    (re.compile(r"测试|QA|质量", re.UNICODE), "测试/QA"),
    # 运维
    (re.compile(r"运维|DevOps|SRE|云平台|系统管理|DBA", re.UNICODE), "运维/DevOps"),
    # 嵌入式
    (re.compile(r"嵌入式|驱动|单片机|RTOS|MCU|FPGA|ARM|DSP|"
                r"硬件|电路|PCB|射频", re.UNICODE), "嵌入式/硬件"),
    # 产品
    (re.compile(r"产品(?:经理|设计|运营|总监|负责人|专员)?|PM\b", re.UNICODE), "产品"),
    # 销售/运营
    (re.compile(r"销售|客户|运营|市场|BD|商务", re.UNICODE), "销售/运营"),
    # C++
    (re.compile(r"C\+\+|C语言|Qt|MFC", re.UNICODE), "C++开发"),
    # 安全
    (re.compile(r"安全|渗透|逆向|加密", re.UNICODE), "安全"),
]

def normalize_title(title: str) -> tuple[str, str, str]:
    """
    标准化职位名称。
    
    Returns:
        (normalized_title, level, family)
    """
    t = _TITLE_STRIP_RE.sub("", title).strip().rstrip("-—–·•()（）").strip()
    
    level = "mid"
    for pat, lv in _LEVEL_PREFIX_MAP:
        if pat.search(t):
            level = lv
            t = pat.sub("", t).strip()
            break
    
    family = "其他"
    for pat, fam in _FAMILY_MAP:
        if pat.search(t):
            family = fam
            break
    
    return t, level, family


# ── 数据加载 ──────────────────────────────────────────────────────

@dataclass
class JobRecord:
    id: int = 0
    title: str = ""
    title_norm: str = ""
    title_level: str = "mid"
    title_family: str = "其他"
    city: str = ""
    company: str = ""
    salary_avg: float = 0.0
    salary_min: float = 0.0
    salary_max: float = 0.0
    salary_unit: str = "month"
    experience: str = ""
    education: str = ""
    skills: list = field(default_factory=list)
    tags: list = field(default_factory=list)


def load_jobs(db_path: str, family_filter: str = None, city_filter: str = None) -> list[JobRecord]:
    """从数据库加载岗位记录，完成标题标准化。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    sql = """
        SELECT id, title, city, company_name as company,
               salary_avg, salary_min, salary_max, salary_unit,
               experience, education, skills
        FROM jobs
        WHERE salary_avg > 0 AND salary_avg/1000 < 100
    """
    params = []
    if city_filter:
        sql += " AND city = ?"
        params.append(city_filter)
    
    cur = conn.execute(sql, params)
    records = []
    for row in cur:
        skills_str = row["skills"] or ""
        skills = [s.strip() for s in skills_str.split(",") if s.strip()]
        
        title_norm, level, family = normalize_title(row["title"])
        
        if family_filter and family_filter != "all" and family != family_filter:
            continue
        
        records.append(JobRecord(
            id=row["id"],
            title=row["title"],
            title_norm=title_norm,
            title_level=level,
            title_family=family,
            city=row["city"] or "未知",
            company=row["company"] or "未知",
            salary_avg=row["salary_avg"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_unit=row["salary_unit"],
            experience=row["experience"] or "",
            education=row["education"] or "",
            skills=skills,
        ))
    
    conn.close()
    return records


# ── 对标分析 ──────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """对标分析结果"""
    # 输入
    title: str
    salary: float
    city: str
    
    # 对标族群
    peer_count: int
    peer_cities: list[str]
    
    # 全市场 (统一为 元/月)
    market_p25: float
    market_p50: float  # 中位数
    market_p75: float
    market_mean: float
    
    # 本城
    city_p25: float
    city_p50: float
    city_p75: float
    city_mean: float
    
    # 定位
    percentile_city: float  # 在本城的百分位
    percentile_market: float
    delta_vs_city: float    # vs 本城中位数的差值
    delta_pct: float        # 差值百分比
    
    # 建议
    assessment: str
    top_skills_required: list[str]
    similar_roles: list[dict]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "salary": int(self.salary),
            "city": self.city,
            "peer_count": self.peer_count,
            "peer_cities": self.peer_cities,
            "market_p50": int(self.market_p50),
            "city_p50": int(self.city_p50),
            "percentile": round(self.percentile_city, 1),
            "delta_vs_city": round(self.delta_vs_city),
            "delta_pct": round(self.delta_pct, 1),
            "assessment": self.assessment,
            "top_skills": self.top_skills_required[:10],
            "similar_roles": self.similar_roles[:5],
        }


class PositionBenchmark:
    """岗位对标引擎"""
    
    def __init__(self, db_path: str = "data/processed/jobs.db"):
        self.db_path = db_path
        self._records: list[JobRecord] = []
        self._by_family: dict[str, list[JobRecord]] = defaultdict(list)
        self._by_city: dict[str, list[JobRecord]] = defaultdict(list)
        self._loaded = False
    
    def load(self, city_filter: str = None):
        self._records = load_jobs(self.db_path, city_filter=city_filter)
        self._by_family.clear()
        self._by_city.clear()
        for r in self._records:
            self._by_family[r.title_family].append(r)
            self._by_city[r.city].append(r)
        self._loaded = True
        return self
    
    def _ensure_loaded(self):
        if not self._loaded:
            self.load()
    
    def _to_monthly(self, r: JobRecord) -> float:
        if r.salary_unit == "year":
            return r.salary_avg / 12
        return r.salary_avg
    
    def benchmark(
        self,
        title: str,
        salary: float,
        city: str,
    ) -> BenchmarkResult:
        """
        对给定岗位和薪资进行市场对标。
        
        Args:
            title: 岗位名称 (如 "Python开发工程师")
            salary: 个人月薪 (元/月)
            city: 所在城市
        
        Returns:
            BenchmarkResult 含完整对标数据
        """
        self._ensure_loaded()
        
        title_norm, level, family = normalize_title(title)
        
        # 找同类岗位 (同 family + 同级或以上)
        peers = [
            j for j in self._records
            if j.title_family == family
            and j.id not in (0,)  # exclude self
        ]
        if not peers:
            peers = [j for j in self._records if j.title_family == family]
        if len(peers) < 5:
            # 族内不够 → 放宽
            peers = [j for j in self._records if j.title_family == family]
        if not peers:
            return BenchmarkResult(
                title=title, salary=salary, city=city,
                peer_count=0, peer_cities=[], assessment="数据不足，无法对标",
                market_p25=0, market_p50=0, market_p75=0, market_mean=0,
                city_p25=0, city_p50=0, city_p75=0, city_mean=0,
                percentile_city=0, percentile_market=0,
                delta_vs_city=0, delta_pct=0,
                top_skills_required=[], similar_roles=[],
            )
        
        peers_city = [j for j in peers if j.city == city]
        if not peers_city:
            peers_city = peers  # 无本城数据 → 用全国
        
        peer_cities = sorted(set(j.city for j in peers))
        
        # ── 统计 ──
        market_salaries = np.array([self._to_monthly(j) for j in peers])
        city_salaries = np.array([self._to_monthly(j) for j in peers_city])
        
        market_p25, market_p50, market_p75 = np.percentile(market_salaries, [25, 50, 75])
        market_mean = float(np.mean(market_salaries))
        
        city_p25, city_p50, city_p75 = np.percentile(city_salaries, [25, 50, 75])
        city_mean = float(np.mean(city_salaries))
        
        # ── 百分位 ──
        percentile_market = (np.sum(market_salaries <= salary) / len(market_salaries)) * 100
        percentile_city = (np.sum(city_salaries <= salary) / len(city_salaries)) * 100
        
        delta = salary - city_p50
        delta_pct = (delta / city_p50 * 100) if city_p50 > 0 else 0
        
        # ── 评估 ──
        if percentile_city >= 90:
            assessment = f"🏆 顶尖水平 (超过 {percentile_city:.0f}% 同城同行)"
        elif percentile_city >= 75:
            assessment = f"📈 高于市场 (超过 {percentile_city:.0f}% 同城同行)"
        elif percentile_city >= 50:
            assessment = f"✅ 中等偏上 (市场定位健康)"
        elif percentile_city >= 25:
            assessment = f"📊 中等偏下 (有议价空间)"
        else:
            assessment = f"⚠️ 低于市场 (仅超过 {percentile_city:.0f}% 同城同行)"
        
        # ── 技能需求 ──
        skill_counter: dict[str, int] = defaultdict(int)
        for j in peers:
            for s in j.skills:
                skill_counter[s] += 1
        top_skills = [k for k, _ in sorted(skill_counter.items(), key=lambda x: -x[1])]
        
        # ── 相似岗位 ──
        title_counter: dict[str, int] = defaultdict(int)
        for j in peers:
            title_counter[j.title] += 1
        similar = [
            {"title": t, "count": c, "avg_salary": int(
                np.mean([self._to_monthly(j) for j in peers if j.title == t])
            )}
            for t, c in sorted(title_counter.items(), key=lambda x: -x[1])[:8]
        ]
        
        return BenchmarkResult(
            title=title, salary=salary, city=city,
            peer_count=len(peers), peer_cities=peer_cities,
            market_p25=market_p25, market_p50=market_p50,
            market_p75=market_p75, market_mean=market_mean,
            city_p25=city_p25, city_p50=city_p50,
            city_p75=city_p75, city_mean=city_mean,
            percentile_city=percentile_city, percentile_market=percentile_market,
            delta_vs_city=delta, delta_pct=delta_pct,
            assessment=assessment,
            top_skills_required=top_skills,
            similar_roles=similar,
        )
    
    def city_heatmap(self, title_family: str = "all", min_count: int = 5) -> dict:
        """跨城市薪资热力数据。"""
        self._ensure_loaded()
        
        records = self._records
        if title_family != "all":
            records = self._by_family.get(title_family, [])
        
        by_city: dict[str, list[float]] = defaultdict(list)
        for r in records:
            by_city[r.city].append(self._to_monthly(r))
        
        result = {}
        for city, salaries in sorted(by_city.items()):
            if len(salaries) < min_count:
                continue
            arr = np.array(salaries)
            result[city] = {
                "p25": int(np.percentile(arr, 25)),
                "p50": int(np.percentile(arr, 50)),
                "p75": int(np.percentile(arr, 75)),
                "mean": int(np.mean(arr)),
                "count": len(salaries),
            }
        return result
    
    def position_gap_analysis(self, title: str) -> dict:
        """单一职位的城市间薪资差距分析。"""
        self._ensure_loaded()
        
        title_norm, level, family = normalize_title(title)
        matching = [
            j for j in self._records
            if j.title_family == family
        ]
        
        by_city: dict[str, list[float]] = defaultdict(list)
        for j in matching:
            by_city[j.city].append(self._to_monthly(j))
        
        cities_data = {}
        for city, salaries in by_city.items():
            if len(salaries) < 3:
                continue
            arr = np.array(salaries)
            cities_data[city] = {
                "median": int(np.median(arr)),
                "mean": int(np.mean(arr)),
                "count": len(salaries),
            }
        
        if not cities_data:
            return {"error": "数据不足"}
        
        medians = {c: d["median"] for c, d in cities_data.items()}
        top_city = max(medians, key=medians.get)
        base_median = min(medians.values()) if medians else 0
        
        return {
            "family": family,
            "level": level,
            "city_count": len(cities_data),
            "total_matches": len(matching),
            "top_city": {"name": top_city, "median": medians[top_city]},
            "spread": int(max(medians.values()) - base_median) if base_median > 0 else 0,
            "cities": cities_data,
        }


# ── CLI ────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="岗位对标分析器")
    parser.add_argument("--db", default="data/processed/jobs.db")
    sub = parser.add_subparsers(dest="cmd")
    
    # benchmark
    bench = sub.add_parser("benchmark")
    bench.add_argument("--title", required=True)
    bench.add_argument("--salary", type=float, required=True)
    bench.add_argument("--city", required=True)
    
    # heatmap
    hm = sub.add_parser("heatmap")
    hm.add_argument("--family", default="all")
    hm.add_argument("--min-count", type=int, default=5)
    
    # gap
    gap = sub.add_parser("gap")
    gap.add_argument("--title", required=True)
    
    args = parser.parse_args()
    bm = PositionBenchmark(args.db).load()
    
    if args.cmd == "benchmark":
        r = bm.benchmark(args.title, args.salary, args.city)
        d = r.to_dict()
        print(f"\n{'='*50}")
        print(f"📊 {d['title']} @ {d['city']}  ¥{d['salary']:,}/月")
        print(f"{'='*50}")
        print(f"  对标族群: {d['peer_count']} 条 ({', '.join(d['peer_cities'][:6])})")
        print(f"  全国 P50: ¥{d['market_p50']:,}/月")
        print(f"  本城 P50: ¥{d['city_p50']:,}/月")
        print(f"  百分位:  {d['percentile']}%")
        print(f"  差值:    {d['delta_vs_city']:+} ({d['delta_pct']:+.1f}%)")
        print(f"  评估:    {d['assessment']}")
        print(f"  TOP技能: {', '.join(d['top_skills'][:8])}")
    
    elif args.cmd == "heatmap":
        heat = bm.city_heatmap(args.family, args.min_count)
        print(f"\n{'='*50}")
        print(f"🏙  跨城市薪资热力 — {args.family}")
        print(f"{'='*50}")
        for city, d in sorted(heat.items(), key=lambda x: -x[1]["p50"]):
            print(f"  {city:8s} P25=¥{d['p25']:>6,}  P50=¥{d['p50']:>6,}  "
                  f"P75=¥{d['p75']:>6,}  均值=¥{d['mean']:>6,}  (n={d['count']})")
    
    elif args.cmd == "gap":
        g = bm.position_gap_analysis(args.title)
        if "error" in g:
            print(g["error"])
        else:
            print(f"\n📊 {args.title} ({g['family']}/{g['level']})")
            print(f"   样本: {g['total_matches']} 条, 覆盖 {g['city_count']} 城市")
            print(f"   最高: {g['top_city']['name']} ¥{g['top_city']['median']:,}")
            print(f"   极差: ¥{g['spread']:,}")
            for c, d in sorted(g["cities"].items(), key=lambda x: -x[1]["median"]):
                print(f"   {c:8s} ¥{d['median']:>6,} (n={d['count']})")


if __name__ == "__main__":
    main()
