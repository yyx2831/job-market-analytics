#!/usr/bin/env python3
"""数据质量 v2 — 薪资异常检测与修复。

三路分类:
  1. 年薪制高值 → 值接近年薪量级, 需 ÷12
  2. 年薪制低值 → 值已是月薪, 仅改 unit label
  3. 日薪制 → 从 salary_text 提取日薪 ×22 转月薪

用法: python3 scripts/fix_salary_anomalies.py [--apply]
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd
import numpy as np

DB_PATH = Path(__file__).parent.parent / "data" / "processed" / "jobs.db"


def classify_yearly(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """年薪制条目: 分类为「需除12」和「仅改label」"""
    to_divide: list[dict] = []
    to_relabel: list[dict] = []

    for _, row in df.iterrows():
        text = str(row.get("salary_text", ""))
        if not text or ("万/年" not in text and "万元/年" not in text):
            continue

        m = re.search(r"(\d+)[-~](\d+)\s*万", text)
        if not m:
            continue

        text_annual_avg = (float(m.group(1)) + float(m.group(2))) / 2 * 10000
        stored_avg = row.get("salary_avg")
        if pd.isna(stored_avg) or stored_avg <= 0:
            continue

        # stored_avg * 12 vs text_annual_avg
        ratio = (stored_avg * 12) / text_annual_avg if text_annual_avg > 0 else 0

        rec = {
            "id": int(row["id"]), "title": str(row["title"])[:30],
            "city": str(row.get("city", "")),
            "salary_text": text[:30],
            "salary_min": row.get("salary_min"),
            "salary_max": row.get("salary_max"),
            "salary_avg": stored_avg,
            "salary_unit": str(row.get("salary_unit", "")),
            "salary_months": row.get("salary_months") or 12,
        }

        if 0.5 < ratio < 2.0:
            # 已是月薪 → 只改 unit label
            to_relabel.append(rec)
        else:
            # 高值 → 需 ÷12
            to_divide.append(rec)

    return to_divide, to_relabel


def detect_daily(df: pd.DataFrame) -> list[dict]:
    """日薪制条目。"""
    results: list[dict] = []
    mask = df["salary_text"].fillna("").str.contains(r"元\s*/\s*[天日]", regex=True)

    for _, row in df[mask].iterrows():
        text = str(row.get("salary_text", ""))
        m = re.search(r"(\d+)\s*元\s*/\s*[天日]", text)
        day_amount = float(m.group(1)) if m else 0
        if day_amount <= 0:
            continue

        results.append({
            "id": int(row["id"]), "title": str(row["title"])[:30],
            "city": str(row.get("city", "")),
            "salary_text": text[:30],
            "salary_avg": row.get("salary_avg"),
            "day_amount": day_amount,
            "month_salary": day_amount * 22,
        })

    return results


def fix_anomalies(db_path: str, dry_run: bool = True) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    df = pd.read_sql("SELECT * FROM jobs", conn)

    # ── 分类 ──
    to_divide, to_relabel = classify_yearly(df)
    daily = detect_daily(df)

    stats = {
        "year_divide": len(to_divide),
        "year_relabel": len(to_relabel),
        "day_fix": len(daily),
    }

    def _fmt(sal):
        if sal is None or pd.isna(sal):
            return "NULL"
        return f"¥{sal/1000:.1f}K"

    print(f"\n{'='*55}")
    print(f"📊 检测: 年薪÷12={len(to_divide)} | 年薪改label={len(to_relabel)} | 日薪={len(daily)}")

    if to_divide:
        print(f"\n── ❶ 年薪制 → 需 ÷12 ({len(to_divide)} 条) ──")
        for r in to_divide:
            new_avg = r["salary_avg"] / 12
            print(f"  [{r['id']}] {r['title']:30s} {r['city']:6s} "
                  f"{_fmt(r['salary_avg'])} → {_fmt(new_avg)} ({r['salary_text']})")

    if to_relabel:
        print(f"\n── ❷ 年薪制 → 仅改 label ({len(to_relabel)} 条) ──")
        for r in to_relabel:
            print(f"  [{r['id']}] {r['title']:30s} {r['city']:6s} "
                  f"{_fmt(r['salary_avg'])}/月(已转换) ({r['salary_text']})")

    if daily:
        print(f"\n── ❸ 日薪制 → ×22 ({len(daily)} 条) ──")
        for r in daily:
            print(f"  [{r['id']}] {r['title']:30s} {r['city']:6s} "
                  f"¥{r['day_amount']}/天 → {_fmt(r['month_salary'])}/月 ({r['salary_text']})")

    if dry_run:
        print(f"\n  👆 DRY RUN。用 --apply 执行写入。")
        conn.close()
        return stats

    # ── 写入 ──
    cursor = conn.cursor()

    for r in to_divide:
        new_min = (r["salary_min"] / 12) if r["salary_min"] and r["salary_min"] > 10000 else r["salary_min"]
        new_max = (r["salary_max"] / 12) if r["salary_max"] and r["salary_max"] > 10000 else r["salary_max"]
        new_avg = r["salary_avg"] / 12
        cursor.execute(
            "UPDATE jobs SET salary_min=?, salary_max=?, salary_avg=?, salary_unit='year' WHERE id=?",
            (new_min, new_max, new_avg, r["id"]),
        )

    for r in to_relabel:
        cursor.execute(
            "UPDATE jobs SET salary_unit='year' WHERE id=?",
            (r["id"],),
        )

    for r in daily:
        cursor.execute(
            "UPDATE jobs SET salary_min=?, salary_max=?, salary_avg=?, salary_unit='month', salary_months=12 WHERE id=?",
            (r["month_salary"], r["month_salary"], r["month_salary"], r["id"]),
        )

    conn.commit()
    conn.close()

    print(f"\n  ✅ 已写入: ÷12={len(to_divide)}, relabel={len(to_relabel)}, 日薪={len(daily)}")
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()

    fix_anomalies(args.db, dry_run=not args.apply)


if __name__ == "__main__":
    main()
