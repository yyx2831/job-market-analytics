#!/usr/bin/env python3
"""
publish_time 数据清洗脚本
- 825 条"今日回复10+次"、"简历处理快"等 → crawl_time 回退
- 1140 条 NULL/空 → crawl_time 回退
- 保留清理统计
"""

import sqlite3
import sys
from datetime import datetime


def is_valid_date(val: str) -> bool:
    """判断是否为有效日期格式（Y20xx开头）"""
    if not val:
        return False
    val = val.strip()
    return val.startswith("20") and len(val) >= 10


def main(db_path: str = "data/processed/jobs.db", dry_run: bool = False):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("⏱️  publish_time 数据清洗")
    print(f"   模式: {'DRY RUN' if dry_run else '实际写入'}")
    print("-" * 60)

    # All jobs with bad publish_time
    cur.execute("""
        SELECT id, publish_time, crawl_time, source FROM jobs
        WHERE publish_time IS NULL OR publish_time = '' 
           OR publish_time NOT LIKE '20%'
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"\n   待清洗: {len(rows)} 条 (NULL{1140} + 脏值{825})")

    # Categorize
    bad_patterns = {}
    fallback_count = 0
    updates = []

    for rid, pub, crawl, source in rows:
        if is_valid_date(pub):
            continue  # already good

        # Use crawl_time as fallback
        fallback = crawl[:10] if crawl and len(crawl) >= 10 else datetime.now().strftime("%Y-%m-%d")

        if pub and pub.strip():
            pattern = pub[:20]
            bad_patterns[pattern] = bad_patterns.get(pattern, 0) + 1

        if not dry_run:
            updates.append((fallback, datetime.now().isoformat(), rid))
        fallback_count += 1

    print(f"\n   脏值模式分布:")
    for pat, cnt in sorted(bad_patterns.items(), key=lambda x: -x[1]):
        print(f"     '{pat}' → {cnt} 条")

    if not dry_run and updates:
        cur.executemany(
            "UPDATE jobs SET publish_time = ?, updated_at = ? WHERE id = ?",
            updates,
        )
        conn.commit()
        print(f"\n   ✅ 已清洗 {len(updates)} 条 (publish_time ← crawl_time)")

    # Verify
    cur.execute("""
        SELECT COUNT(*) FROM jobs 
        WHERE publish_time IS NULL OR publish_time = '' 
           OR publish_time NOT LIKE '20%'
    """)
    remaining = cur.fetchone()[0]
    print(f"\n📈 验证: 仍有脏数据的: {remaining} 条")

    # Show new distribution
    cur.execute("""
        SELECT substr(publish_time,1,7) as yyyy_mm, COUNT(*) 
        FROM jobs WHERE publish_time LIKE '20%'
        GROUP BY yyyy_mm ORDER BY yyyy_mm DESC LIMIT 10
    """)
    print("   修复后日期分布:")
    for r in cur.fetchall():
        print(f"     {r[0]}: {r[1]} 条")

    if dry_run:
        print(f"\n⚠️  DRY RUN — 未实际写入，加 --apply 执行")

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
