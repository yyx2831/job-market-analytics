#!/usr/bin/env python3
"""
增量差异分析脚本 — 对比最近两次 collection_batch 的数据变化。

分析维度：
  - 薪资变化方向（涨 / 跌 / 持平）
  - 新出现技能
  - 新增公司数
  - 城市分布变化

用法:
  python scripts/diff_analysis.py [--db data/processed/jobs.db]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd


def get_recent_batches(conn: sqlite3.Connection, n: int = 2) -> list[tuple[str, int]]:
    """获取最近 n 个有效的 collection_batch（非 NULL、非空的）。"""
    cur = conn.execute("""
        SELECT collection_batch, COUNT(*) as cnt
        FROM jobs
        WHERE collection_batch IS NOT NULL
          AND collection_batch != ''
        GROUP BY collection_batch
        ORDER BY MAX(crawl_time) DESC
        LIMIT ?
    """, (n,))
    return [(r["collection_batch"], r["cnt"]) for r in cur.fetchall()]


def load_batch(conn: sqlite3.Connection, batch_name: str) -> pd.DataFrame:
    """加载指定批次的岗位数据。"""
    return pd.read_sql("""
        SELECT *
        FROM jobs
        WHERE collection_batch = ?
    """, conn, params=(batch_name,))


def analyze_diff(df_prev: pd.DataFrame, df_curr: pd.DataFrame,
                 batch_prev: str, batch_curr: str) -> str:
    """
    对比两个批次的数据，生成差异分析报告。

    Returns:
        Markdown 格式的分析报告。
    """
    lines: list[str] = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append(f"# 📊 增量差异分析报告")
    lines.append(f"")
    lines.append(f"**生成时间**: {now_str}")
    lines.append(f"**前一批次**: `{batch_prev}` ({len(df_prev):,} 条)")
    lines.append(f"**当前批次**: `{batch_curr}` ({len(df_curr):,} 条)")
    lines.append(f"")

    # ━━━ 1. 规模变化 ━━━
    lines.append(f"## 1. 规模变化")
    lines.append(f"")
    delta_count = len(df_curr) - len(df_prev)
    lines.append(f"| 指标 | 前一批次 | 当前批次 | 变化 |")
    lines.append(f"|------|---------|---------|------|")
    lines.append(f"| 岗位数 | {len(df_prev):,} | {len(df_curr):,} | {delta_count:+d} ({delta_count / max(len(df_prev), 1) * 100:+.1f}%) |")

    prev_companies = df_prev["company_name"].nunique() if "company_name" in df_prev.columns else 0
    curr_companies = df_curr["company_name"].nunique() if "company_name" in df_curr.columns else 0
    delta_companies = curr_companies - prev_companies
    lines.append(f"| 公司数 | {prev_companies:,} | {curr_companies:,} | {delta_companies:+d} |")

    prev_cities = df_prev["city"].nunique() if "city" in df_prev.columns else 0
    curr_cities = df_curr["city"].nunique() if "city" in df_curr.columns else 0
    delta_cities = curr_cities - prev_cities
    lines.append(f"| 城市数 | {prev_cities:,} | {curr_cities:,} | {delta_cities:+d} |")
    lines.append(f"")

    # ━━━ 2. 薪资变化 ━━━
    lines.append(f"## 2. 薪资变化")
    lines.append(f"")

    prev_sal = df_prev[df_prev["salary_avg"] > 0]["salary_avg"]
    curr_sal = df_curr[df_curr["salary_avg"] > 0]["salary_avg"]

    if len(prev_sal) > 0 and len(curr_sal) > 0:
        prev_mean = prev_sal.mean()
        curr_mean = curr_sal.mean()
        prev_median = prev_sal.median()
        curr_median = curr_sal.median()
        prev_p25 = np.percentile(prev_sal, 25)
        curr_p25 = np.percentile(curr_sal, 25)
        prev_p75 = np.percentile(prev_sal, 75)
        curr_p75 = np.percentile(curr_sal, 75)

        lines.append(f"| 指标 | 前一批次 | 当前批次 | 变化 | 方向 |")
        lines.append(f"|------|---------|---------|------|------|")
        lines.append(f"| 均薪 | ¥{prev_mean:,.0f} | ¥{curr_mean:,.0f} | ¥{curr_mean - prev_mean:+,.0f} | {'📈 涨' if curr_mean > prev_mean else '📉 跌'} |")
        lines.append(f"| 中位数 | ¥{prev_median:,.0f} | ¥{curr_median:,.0f} | ¥{curr_median - prev_median:+,.0f} | {'📈 涨' if curr_median > prev_median else '📉 跌'} |")
        lines.append(f"| P25 | ¥{prev_p25:,.0f} | ¥{curr_p25:,.0f} | ¥{curr_p25 - prev_p25:+,.0f} | — |")
        lines.append(f"| P75 | ¥{prev_p75:,.0f} | ¥{curr_p75:,.0f} | ¥{curr_p75 - prev_p75:+,.0f} | — |")
        lines.append(f"")

        # 判断总体薪资方向
        if curr_mean > prev_mean * 1.02:
            lines.append(f"> 📈 **薪资趋势：上涨** (均薪上涨 {((curr_mean - prev_mean) / prev_mean * 100):+.1f}%)")
        elif curr_mean < prev_mean * 0.98:
            lines.append(f"> 📉 **薪资趋势：下跌** (均薪下跌 {((curr_mean - prev_mean) / prev_mean * 100):+.1f}%)")
        else:
            lines.append(f"> ➡️ **薪资趋势：持平** (变化在 ±2% 以内)")
        lines.append(f"")

        # 按城市细分
        lines.append(f"### 各城市薪资变化 (TOP 10)")
        lines.append(f"")
        lines.append(f"| 城市 | 前均薪 | 现均薪 | 变化 | 方向 |")
        lines.append(f"|------|--------|--------|------|------|")

        cities_prev = df_prev[df_prev["salary_avg"] > 0].groupby("city")["salary_avg"].agg(["mean", "count"])
        cities_curr = df_curr[df_curr["salary_avg"] > 0].groupby("city")["salary_avg"].agg(["mean", "count"])

        all_cities = sorted(
            set(cities_prev.index) & set(cities_curr.index),
            key=lambda c: -max(cities_prev.loc[c, "count"] if c in cities_prev.index else 0,
                               cities_curr.loc[c, "count"] if c in cities_curr.index else 0),
        )[:10]

        for city in all_cities:
            prev_m = cities_prev.loc[city, "mean"] if city in cities_prev.index else 0
            curr_m = cities_curr.loc[city, "mean"] if city in cities_curr.index else 0
            diff_m = curr_m - prev_m
            direction = "📈" if diff_m > 0 else ("📉" if diff_m < 0 else "➡️")
            lines.append(f"| {city} | ¥{prev_m:,.0f} | ¥{curr_m:,.0f} | ¥{diff_m:+,.0f} | {direction} |")
        lines.append(f"")

    else:
        lines.append(f"⚠️ 薪资数据不足，无法分析。")
        lines.append(f"")

    # ━━━ 3. 新增技能分析 ━━━
    lines.append(f"## 3. 技能变化")
    lines.append(f"")

    def extract_skills(df: pd.DataFrame) -> Counter:
        counter: Counter = Counter()
        for skills_str in df["skills"].dropna():
            for s in str(skills_str).split(","):
                s = s.strip()
                if s:
                    counter[s] += 1
        return counter

    prev_skills = extract_skills(df_prev)
    curr_skills = extract_skills(df_curr)

    new_skills = set(curr_skills.keys()) - set(prev_skills.keys())
    disappeared_skills = set(prev_skills.keys()) - set(curr_skills.keys())

    if new_skills:
        sorted_new = sorted(new_skills, key=lambda s: -curr_skills[s])
        lines.append(f"### 🆕 新出现技能 ({len(new_skills)} 个)")
        lines.append(f"")
        for sk in sorted_new[:20]:
            lines.append(f"- **{sk}** — 出现 {curr_skills[sk]} 次")
        if len(new_skills) > 20:
            lines.append(f"- ... 及其他 {len(new_skills) - 20} 个")
        lines.append(f"")

    if disappeared_skills:
        sorted_gone = sorted(disappeared_skills, key=lambda s: -prev_skills[s])
        lines.append(f"### ❌ 消失技能 ({len(disappeared_skills)} 个)")
        lines.append(f"")
        for sk in sorted_gone[:10]:
            lines.append(f"- **{sk}** — 前次出现 {prev_skills[sk]} 次")
        lines.append(f"")

    # 技能渗透率变化 TOP 10
    lines.append(f"### 📊 技能渗透率变化 TOP 10")
    lines.append(f"")
    lines.append(f"| 技能 | 前批渗透率 | 当前渗透率 | 变化 |")
    lines.append(f"|------|-----------|-----------|------|")

    total_prev = max(len(df_prev), 1)
    total_curr = max(len(df_curr), 1)
    all_common = sorted(
        set(prev_skills.keys()) | set(curr_skills.keys()),
        key=lambda s: -(prev_skills.get(s, 0) / total_prev + curr_skills.get(s, 0) / total_curr)
    )[:15]

    for sk in all_common:
        prev_pen = prev_skills.get(sk, 0) / total_prev * 100
        curr_pen = curr_skills.get(sk, 0) / total_curr * 100
        diff_pen = curr_pen - prev_pen
        if abs(diff_pen) > 0.05:  # Only show meaningful changes
            lines.append(f"| {sk} | {prev_pen:.1f}% | {curr_pen:.1f}% | {diff_pen:+.1f}% |")
    lines.append(f"")

    # ━━━ 4. 新增公司 ━━━
    lines.append(f"## 4. 公司变化")
    lines.append(f"")

    prev_co = set(df_prev["company_name"].dropna().unique()) if "company_name" in df_prev else set()
    curr_co = set(df_curr["company_name"].dropna().unique()) if "company_name" in df_curr else set()
    new_companies = curr_co - prev_co

    lines.append(f"- 前批公司数: {len(prev_co):,}")
    lines.append(f"- 当前公司数: {len(curr_co):,}")
    lines.append(f"- 新增公司数: {len(new_companies):,}")
    lines.append(f"- 消失公司数: {len(prev_co - curr_co):,}")
    lines.append(f"")

    if new_companies:
        # 新增公司中岗位最多的 TOP 10
        new_co_counts = df_curr[df_curr["company_name"].isin(new_companies)]["company_name"].value_counts()
        lines.append(f"### 🏢 新增公司 TOP 10")
        lines.append(f"")
        lines.append(f"| 公司 | 新增岗位数 |")
        lines.append(f"|------|----------|")
        for co, cnt in new_co_counts.head(10).items():
            lines.append(f"| {co} | {cnt} |")
        lines.append(f"")

    # ━━━ 5. 城市分布变化 ━━━
    lines.append(f"## 5. 城市分布变化")
    lines.append(f"")

    prev_city = df_prev["city"].value_counts() if "city" in df_prev else pd.Series(dtype=int)
    curr_city = df_curr["city"].value_counts() if "city" in df_curr else pd.Series(dtype=int)

    lines.append(f"| 城市 | 前批岗位 | 当前岗位 | 变化 |")
    lines.append(f"|------|---------|---------|------|")

    all_c = sorted(
        set(prev_city.index) | set(curr_city.index),
        key=lambda c: -(prev_city.get(c, 0) + curr_city.get(c, 0))
    )[:15]

    for city in all_c:
        p = prev_city.get(city, 0)
        c = curr_city.get(city, 0)
        lines.append(f"| {city} | {p} | {c} | {c - p:+d} |")
    lines.append(f"")

    # ━━━ 6. 总结 ━━━
    lines.append(f"## 6. 总结")
    lines.append(f"")
    lines.append(f"- **规模**: 从 {len(df_prev):,} 条增长至 {len(df_curr):,} 条 ({delta_count:+d})")
    if len(prev_sal) > 0 and len(curr_sal) > 0:
        lines.append(f"- **薪资**: 均薪 ¥{prev_mean:,.0f} → ¥{curr_mean:,.0f} ({((curr_mean - prev_mean) / prev_mean * 100):+.1f}%)")
    lines.append(f"- **公司**: {prev_companies:,} → {curr_companies:,} ({delta_companies:+d})")
    lines.append(f"- **新技能**: {len(new_skills):,} 个新技能出现")
    lines.append(f"")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="增量差异分析 — 对比最近两次 collection_batch")
    parser.add_argument("--db", default="data/processed/jobs.db", help="SQLite 数据库路径")
    parser.add_argument("--output", help="输出文件路径（可选，默认 stdout + reports/diff_YYYYMMDD.md）")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    batches = get_recent_batches(conn)
    if len(batches) < 2:
        print(f"❌ 批次不足：需要至少 2 个有效批次，当前 {len(batches)} 个")
        conn.close()
        sys.exit(1)

    batch_curr_name, batch_curr_count = batches[0]
    batch_prev_name, batch_prev_count = batches[1]
    print(f"📊 对比批次:")
    print(f"   当前: {batch_curr_name} ({batch_curr_count} 条)")
    print(f"   前批: {batch_prev_name} ({batch_prev_count} 条)")

    df_curr = load_batch(conn, batch_curr_name)
    df_prev = load_batch(conn, batch_prev_name)
    conn.close()

    report = analyze_diff(df_prev, df_curr, batch_prev_name, batch_curr_name)

    # 输出到 stdout
    print()
    print(report)

    # 写入 reports/diff_YYYYMMDD.md
    date_str = datetime.now().strftime("%Y%m%d")
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else (reports_dir / f"diff_{date_str}.md")
    output_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 报告已保存至: {output_path}")


if __name__ == "__main__":
    main()
