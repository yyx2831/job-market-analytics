#!/usr/bin/env python3
"""
来源去重脚本
1. 同 source 去重：title+company+city 相同 → 保留信息最完整的那条
2. 跨 source 去重：只保留 1 条，优先 source 可靠性排序:
   job51 > 51job > lagou > boss > liepin
3. 同 source_job_id 去重（精确匹配）

策略：保留优先条目，删除其余，删前行输出统计
"""

import sqlite3
import sys
from datetime import datetime
from collections import defaultdict


# Source priority (lower = better, more reliable data)
SOURCE_PRIORITY = {
    "job51": 1,    # latest scraper, best data quality
    "51job": 2,    # old scraper
    "lagou": 3,
    "boss": 4,
    "liepin": 5,
    "manual": 0,   # manual entries are the most reliable
}


def dedup_key(row):
    """Generate dedup key from title+company+city (case-insensitive, trim)"""
    title = (row["title"] or "").strip().lower()
    company = (row["company_name"] or "").strip().lower()
    city = (row["city"] or "").strip().lower()
    # Remove common fluff
    for fluff in ["有限公司", "股份有限公司", "有限责任公司", "（", "）", "(", ")"]:
        company = company.replace(fluff, "")
    return f"{title}|{company[:20]}|{city}"


def row_quality(row):
    """
    Quality score for keeping the best row:
    - Has description (+5)
    - Longer description (+len/100)
    - Has salary (+5)
    - Has skills (+3)
    - Has industry (+2)
    - Has company_size (+2)
    - Better source (+3)
    """
    score = 0
    if row["description"] and len(row["description"]) > 50:
        score += 5 + min(len(row["description"]) // 200, 5)
    if row["salary_avg"]:
        score += 5
    if row["skills"]:
        score += 3
    if row["industry"]:
        score += 2
    if row["company_size"]:
        score += 2
    # Source priority bonus
    src = row["source"] or ""
    sp = SOURCE_PRIORITY.get(src, 10)
    score += max(0, 5 - sp)  # lower priority number = higher bonus
    return score


def main(db_path: str = "data/processed/jobs.db", dry_run: bool = True):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("🔗 来源去重")
    print(f"   模式: {'DRY RUN' if dry_run else '实际执行'}")
    print("-" * 60)

    # Fetch all jobs
    cur.execute("""
        SELECT id, title, company_name, city, source, source_job_id,
               description, salary_avg, skills, industry, company_size
        FROM jobs ORDER BY id
    """)
    rows = [dict(r) for r in cur.fetchall()]

    # ---- Pass 1: same source_job_id dedup ----
    by_sjid = defaultdict(list)
    for r in rows:
        sjid = r["source_job_id"]
        if sjid:
            by_sjid[f"{r['source']}|{sjid}"].append(r)

    sjid_dup_ids = set()
    for key, group in by_sjid.items():
        if len(group) > 1:
            group.sort(key=lambda r: row_quality(r), reverse=True)
            for r in group[1:]:
                sjid_dup_ids.add(r["id"])
    print(f"\n   同 source_job_id 去重: {len(sjid_dup_ids)} 条待删")

    # ---- Pass 2: cross-source dedup (by title+company+city) ----
    by_key = defaultdict(list)
    for r in rows:
        if r["id"] in sjid_dup_ids:
            continue
        key = dedup_key(r)
        by_key[key].append(r)

    dup_ids = set()
    dedup_detail = []
    for key, group in by_key.items():
        if len(group) > 1:
            # Sort by quality, keep best
            group.sort(key=lambda r: (SOURCE_PRIORITY.get(r["source"], 10), -row_quality(r)))
            keeper = group[0]
            for r in group[1:]:
                dup_ids.add(r["id"])
                dedup_detail.append((key, r["source"], r["title"]))

    total_to_delete = len(sjid_dup_ids | dup_ids)
    print(f"   交叉去重 (title+company+city): {len(dup_ids)} 条待删")
    print(f"   ──────────────────────────────────")
    print(f"   总计待删: {total_to_delete} 条")
    print(f"   保留: {len(rows) - total_to_delete} 条")

    # Show by source
    delete_by_source = defaultdict(int)
    for r in rows:
        if r["id"] in (sjid_dup_ids | dup_ids):
            delete_by_source[r["source"]] += 1
    print(f"\n   按来源待删分布:")
    for src, cnt in sorted(delete_by_source.items(), key=lambda x: -x[1]):
        print(f"     {src:10s}: {cnt:4d} 条")

    if dry_run:
        # Show some examples
        print(f"\n   示例重复 (前10):")
        for key, src, title in dedup_detail[:10]:
            print(f"     [{src:8s}] {title[:40]}")
        print(f"\n⚠️  DRY RUN — 用 --apply 执行实际删除")
    else:
        # Execute deletion
        all_ids = sjid_dup_ids | dup_ids
        batch_size = 500
        id_list = list(all_ids)
        total_deleted = 0

        for i in range(0, len(id_list), batch_size):
            batch = id_list[i:i + batch_size]
            placeholders = ",".join("?" for _ in batch)
            cur.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", batch)
            total_deleted += cur.rowcount

        conn.commit()
        print(f"\n   ✅ 已删除 {total_deleted} 条重复数据")

        # Vacuum to reclaim space
        cur.execute("VACUUM")
        print(f"   ✅ VACUUM 完成")

        # Verify
        cur.execute("SELECT COUNT(*) FROM jobs")
        remaining = cur.fetchone()[0]
        print(f"\n📈 去重后总数: {remaining} 条")

        # Re-check duplicates
        cur.execute("""
            SELECT COUNT(*) - COUNT(DISTINCT 
                title || '|' || COALESCE(company_name,'') || '|' || COALESCE(city,''))
            FROM jobs
        """)
        new_dups = cur.fetchone()[0]
        print(f"   残留重复: {new_dups} 条")

    conn.close()
    return 0


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    main(dry_run=dry_run)
