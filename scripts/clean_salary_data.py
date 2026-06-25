#!/usr/bin/env python3
"""
薪资数据质量修复脚本
1. salary_months 缺失 → 从 salary_text 提取或默认 12
2. salary_avg 缺失 → 从 (min+max)/2 计算
3. salary_unit 缺失 → 从 salary_text 推断
"""

import sqlite3
import re
import sys
from datetime import datetime


def extract_months(salary_text: str) -> int:
    """从 salary_text 提取发薪月数"""
    if not salary_text:
        return 12
    m = re.search(r'·(\d+)薪', salary_text)
    if m:
        return int(m.group(1))
    return 12


def extract_unit(salary_text: str) -> str:
    """从 salary_text 推断薪资单位"""
    if not salary_text:
        return "month"
    if '/年' in salary_text or '万年' in salary_text or '元/年' in salary_text:
        return "year"
    if '/天' in salary_text or '元/天' in salary_text:
        return "day"
    return "month"


def main(db_path: str = "data/processed/jobs.db", dry_run: bool = False):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print(f"📊 薪资数据质量修复")
    print(f"   数据库: {db_path}")
    print(f"   模式: {'DRY RUN (不写入)' if dry_run else '实际写入'}")
    print("-" * 60)

    # ---- 1. salary_months 修复 ----
    cur.execute(
        "SELECT id, salary_text, salary_months FROM jobs "
        "WHERE salary_months IS NULL AND salary_text IS NOT NULL AND salary_text != ''"
    )
    rows = cur.fetchall()
    print(f"\n🧩 1. salary_months 修复 (NULL → 从 salary_text 提取)")
    print(f"   待修复: {len(rows)} 条")

    stats_months = {}
    updates_months = []
    for rid, stext, _ in rows:
        months = extract_months(stext)
        stats_months[months] = stats_months.get(months, 0) + 1
        if not dry_run:
            updates_months.append((months, rid))

    for m, c in sorted(stats_months.items()):
        print(f"     → {m}个月: {c} 条")

    if not dry_run and updates_months:
        cur.executemany(
            "UPDATE jobs SET salary_months = ?, updated_at = ? WHERE id = ?",
            [(m, datetime.now().isoformat(), rid) for m, rid in updates_months],
        )
        print(f"    ✅ 已修复 {len(updates_months)} 条")

    # ---- 2. salary_avg 修复 ----
    cur.execute(
        "SELECT id, salary_min, salary_max FROM jobs "
        "WHERE salary_avg IS NULL AND salary_min IS NOT NULL AND salary_max IS NOT NULL"
    )
    rows = cur.fetchall()
    print(f"\n🧩 2. salary_avg 修复 (NULL → (min+max)/2)")
    print(f"   待修复: {len(rows)} 条")

    if not dry_run and rows:
        updates_avg = [(int((r[1] + r[2]) / 2), datetime.now().isoformat(), r[0]) for r in rows]
        cur.executemany(
            "UPDATE jobs SET salary_avg = ?, updated_at = ? WHERE id = ?",
            updates_avg,
        )
        print(f"    ✅ 已修复 {len(rows)} 条")
    elif rows:
        # Dry run: show what would be done
        sample = rows[:5]
        for r in sample:
            print(f"    ID={r[0]} min={r[1]} max={r[2]} → avg={int((r[1]+r[2])/2)}")

    # ---- 3. salary_unit 修复 ----
    cur.execute(
        "SELECT id, salary_text FROM jobs "
        "WHERE salary_unit IS NULL AND salary_text IS NOT NULL AND salary_text != ''"
    )
    rows = cur.fetchall()
    print(f"\n🧩 3. salary_unit 修复 (NULL → 从 salary_text 推断)")
    print(f"   待修复: {len(rows)} 条")

    stats_units = {}
    updates_unit = []
    for rid, stext in rows:
        unit = extract_unit(stext)
        stats_units[unit] = stats_units.get(unit, 0) + 1
        if not dry_run:
            updates_unit.append((unit, datetime.now().isoformat(), rid))

    for u, c in sorted(stats_units.items()):
        print(f"     → '{u}': {c} 条")

    if not dry_run and updates_unit:
        cur.executemany(
            "UPDATE jobs SET salary_unit = ?, updated_at = ? WHERE id = ?",
            updates_unit,
        )
        print(f"    ✅ 已修复 {len(updates_unit)} 条")

    # ---- 4. 无 salary_text 但有 salary_min/max 的 NULL months ----
    cur.execute(
        "SELECT id FROM jobs "
        "WHERE salary_months IS NULL AND (salary_text IS NULL OR salary_text = '') "
        "AND salary_min IS NOT NULL"
    )
    no_text_rows = cur.fetchall()
    if no_text_rows:
        print(f"\n🧩 4. salary_months 修复 (无 salary_text, 默认 12)")
        print(f"   待修复: {len(no_text_rows)} 条")
        if not dry_run:
            cur.executemany(
                "UPDATE jobs SET salary_months = 12, updated_at = ? WHERE id = ?",
                [(datetime.now().isoformat(), r[0]) for r in no_text_rows],
            )
            print(f"    ✅ 已修复 {len(no_text_rows)} 条")

    # ---- 提交 ----
    if not dry_run:
        conn.commit()
        print(f"\n💾 已提交到数据库")
    else:
        print(f"\n⚠️  DRY RUN — 未实际写入，请加 --apply 执行")

    # ---- 验证 ----
    print(f"\n📈 验证结果:")
    cur.execute("SELECT COUNT(*) FROM jobs WHERE salary_months IS NULL")
    rem_months = cur.fetchone()[0]
    print(f"   salary_months 仍为 NULL: {rem_months} 条")

    cur.execute("SELECT COUNT(*) FROM jobs WHERE salary_avg IS NULL AND salary_min IS NOT NULL")
    rem_avg = cur.fetchone()[0]
    print(f"   salary_avg 仍为 NULL (有min): {rem_avg} 条")

    cur.execute("SELECT COUNT(*) FROM jobs WHERE salary_unit IS NULL")
    rem_unit = cur.fetchone()[0]
    print(f"   salary_unit 仍为 NULL: {rem_unit} 条")

    conn.close()
    return 0


if __name__ == "__main__":
    dry_run = True
    db_path = "data/processed/jobs.db"

    args = sys.argv[1:]
    if "--apply" in args:
        dry_run = False
    if "--db" in args:
        idx = args.index("--db") + 1
        if idx < len(args):
            db_path = args[idx]

    sys.exit(main(db_path, dry_run))
