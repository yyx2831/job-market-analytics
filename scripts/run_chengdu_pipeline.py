#!/usr/bin/env python3
"""成都岗位数据管道 - 一键采集+入库+刷新。

用法:
    python3 scripts/run_chengdu_pipeline.py
    python3 scripts/run_chengdu_pipeline.py --skip-collect  # 仅入库已有文件
"""
import json, os, re, sqlite3, subprocess, sys, time
from pathlib import Path

PROJECT = Path("/Users/yangyuxiao/codes/job-market-analytics")
DB = PROJECT / "data" / "processed" / "jobs.db"
RAW_DIR = PROJECT / "data" / "raw"

# Mock source names to exclude
MOCK_SOURCES = {"51job", "boss", "lagou", "liepin"}


def import_jsonl(jsonl_path: Path) -> dict:
    """将 DOM 采集的 JSONL 入库（增量 upsert）。"""
    if not jsonl_path.exists():
        return {"error": f"文件不存在: {jsonl_path}"}

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    inserted, skipped, errors = 0, 0, 0
    cities = {}
    keywords = {}

    with open(jsonl_path) as f:
        for line_no, line in enumerate(f, 1):
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                errors += 1
                continue

            title = (j.get("title") or "").strip()
            if not title:
                skipped += 1
                continue

            company = (j.get("company") or "").strip()
            area = (j.get("area") or "").strip()
            salary_text = (j.get("salary") or "").strip()

            # Parse area → city + district
            parts = re.split(r'[·\s\-]+', area)
            city = parts[0] if len(parts) >= 1 else j.get("_city", "")
            district = parts[1] if len(parts) >= 2 else None

            # Parse salary
            sal_min = sal_max = sal_avg = None
            sal_months = 12
            m = re.search(r'(\d+)\s*薪', salary_text)
            if m:
                sal_months = int(m.group(1))
            s_clean = re.sub(r'[·◆]\s*\d+\s*薪', '', salary_text)
            nums = re.findall(r'[\d.]+', s_clean)
            # Determine unit (万/千/none)
            unit = 10000 if '万' in s_clean else (1000 if '千' in s_clean else 1000)
            if len(nums) >= 2:
                lo = float(nums[0])
                hi = float(nums[1])
                sal_min = int(lo * unit)
                sal_max = int(hi * unit)
                if unit == 1000 and sal_max > 50000:
                    sal_max = int(hi * 10000)
                sal_avg = (sal_min + sal_max) // 2
            elif len(nums) == 1:
                val = int(float(nums[0]) * unit)
                sal_min = sal_max = sal_avg = val

            info_text = j.get("info", "")
            # Extract experience and education from info
            exp = edu = industry = co_size = None
            info_parts = [p.strip() for p in info_text.split("|") if p.strip()]
            for part in info_parts:
                part_clean = part.strip()
                if any(w in part_clean for w in ["年经验", "经验", "应届", "在校"]):
                    exp = part_clean
                elif any(w in part_clean for w in ["大专", "本科", "硕士", "博士", "学历"]):
                    edu = part_clean
                elif any(w in part_clean for w in ["人", "员工", "公司规模"]):
                    co_size = part_clean
                elif len(part_clean) >= 3 and not exp and not edu:
                    industry = part_clean

            source_url = j.get("link", "")
            dedupe_key = source_url if source_url else f"dom_{title}_{company}_{j.get('_keyword','')}"
            kw = j.get("_keyword", "")

            try:
                cur.execute("""
                    INSERT OR IGNORE INTO jobs (
                        source, title, company_name, city, district,
                        salary_text, salary_min, salary_max, salary_avg, salary_months,
                        experience, education, industry, company_size,
                        source_url, publish_time, crawl_time, created_at, updated_at,
                        dedupe_key, skills
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "51job_dom", title, company, city, district,
                    salary_text, sal_min, sal_max, sal_avg, sal_months,
                    exp, edu, industry, co_size,
                    source_url, j.get("date", ""), now, now, now,
                    dedupe_key, kw
                ))
                if cur.rowcount > 0:
                    inserted += 1
                    cities[city] = cities.get(city, 0) + 1
                    keywords[kw] = keywords.get(kw, 0) + 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                if errors <= 2:
                    print(f"  DB Error L{line_no}: {e}")

    conn.commit()

    # Summary
    cur.execute("SELECT COUNT(*) FROM jobs")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM jobs WHERE city='成都' AND source NOT IN (?,?,?,?,?)",
                tuple(MOCK_SOURCES) + ("51job_dom",))
    real_before = cur.fetchone()[0] if MOCK_SOURCES else 0
    cur.execute("SELECT COUNT(*) FROM jobs WHERE source='51job_dom' AND city='成都'")
    chengdu_dom = cur.fetchone()[0]
    conn.close()

    return {
        "file": str(jsonl_path),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "db_total": total,
        "chengdu_dom": chengdu_dom,
        "cities": cities,
        "keywords": keywords,
    }


def generate_report(stats: dict):
    """生成采集报告。"""
    print("\n" + "=" * 55)
    print("  📊 成都岗位数据管道 - 执行报告")
    print("=" * 55)
    print(f"\n  📥 采集文件: {stats.get('file', 'N/A')}")
    print(f"  ✅ 新增入库: {stats.get('inserted', 0)} 条")
    print(f"  ⏭️ 去重跳过: {stats.get('skipped', 0)} 条")
    print(f"  ❌ 错误: {stats.get('errors', 0)} 条")
    print(f"  📦 DB总计: {stats.get('db_total', 0)} 条")
    print(f"  🔴 成都真实数据: {stats.get('chengdu_dom', 0)} 条 (51job_dom源)")

    kw = stats.get("keywords", {})
    if kw:
        top_kw = sorted(kw.items(), key=lambda x: -x[1])[:10]
        print(f"\n  🏷️  关键词入库 TOP10:")
        for k, v in top_kw:
            print(f"    {k:12s} {v:4d} 条")

    print(f"\n  🚀 http://localhost:8502")
    print("=" * 55)


def main():
    skip_collect = "--skip-collect" in sys.argv

    # 1. Find latest JSONL
    jsonl_files = sorted(RAW_DIR.glob("job51_*_dom*.jsonl"))
    if not jsonl_files:
        print("❌ 未找到 JSONL 文件，请先运行采集脚本。")
        sys.exit(1)

    # Use the most recent or specified
    jsonl_path = jsonl_files[-1]
    for a in sys.argv:
        if a.endswith(".jsonl"):
            jsonl_path = Path(a)

    print(f"📄 数据文件: {jsonl_path}")

    # 2. Import
    print("📥 开始入库...")
    stats = import_jsonl(jsonl_path)
    if "error" in stats:
        print(f"❌ {stats['error']}")
        sys.exit(1)

    generate_report(stats)


if __name__ == "__main__":
    main()
