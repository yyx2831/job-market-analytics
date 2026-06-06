"""采集入口脚本。

用法:
  python scripts/run_spider.py --source job51 --city 成都 --keywords Python Java --limit 50
  python scripts/run_spider.py --source company_site --site meituan --city 成都 --limit 30
  python scripts/run_spider.py --source all --city 成都 --limit 100
  python scripts/run_spider.py --source job51_xbrowser --city 成都 --all-keywords --limit-per-kw 50
  python scripts/run_spider.py --source job51_xbrowser --cities 上海 北京 深圳 --keywords Python --limit-per-kw 40
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scraping.sources import CompanySiteCollector, Job51Collector, Job51XBrowserCollector
from src.scraping.pipeline import pipeline
from src.scraping.quality import generate_quality_report, print_report, save_report
from src.scraping.anti_crawl import city_interval_sleep
from src.database import connect, import_csv, import_csv_with_stats, init_db, record_crawl_run


DEFAULT_KEYWORDS = [
    "Python", "Java", "前端", "数据分析", "测试",
    "运维", "产品经理", "UI设计", "运营", "销售",
]

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = PROCESSED_DIR / "reports"
DB_PATH = PROCESSED_DIR / "jobs.db"


def run_job51(city: str, keywords: list[str], limit: int, enrich_detail: bool = False) -> None:
    collector = Job51Collector(RAW_DIR / "job51")
    t0 = time.monotonic()

    raw_jobs = collector.collect(
        city=city, keywords=keywords,
        max_pages_per_keyword=3,
        max_jobs_total=limit,
        enrich_detail=enrich_detail,
    )

    duration = time.monotonic() - t0
    print(f"\n采集完成: {len(raw_jobs)} raw jobs in {duration:.1f}s")

    if not raw_jobs:
        print("无数据，跳过后续步骤。")
        return

    _process_results(collector, raw_jobs, duration)


def run_job51_xbrowser(city: str, keywords: list[str], limit: int) -> None:
    """通过 xbrowser (真实 Chrome) 调用 51job API 采集。"""
    collector = Job51XBrowserCollector(
        output_dir=RAW_DIR,
        max_pages=50,
        # 使用类默认的 WAF 安全速率 (15-30s)，不覆盖
    )
    start_ts = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    t0 = time.monotonic()

    raw_jobs = collector.collect(
        city=city,
        keywords=keywords,
        max_pages_per_keyword=min(5, limit // 20 + 1),
        max_jobs_total=limit,
    )

    duration = time.monotonic() - t0
    print(f"\n采集完成: {len(raw_jobs)} raw jobs in {duration:.1f}s")

    if not raw_jobs:
        print("无数据，跳过后续步骤。")
        return

    _process_xbrowser_results(
        collector, raw_jobs, duration,
        city=city, keywords=keywords, start_ts=start_ts,
    )


def run_company_site(city: str, keywords: list[str], limit: int, site: str = "all") -> None:
    sites = [site] if site != "all" else CompanySiteCollector.available_sites()
    all_raw: list = []

    for site_name in sites:
        print(f"\n--- 采集 {site_name} ---")
        collector = CompanySiteCollector(RAW_DIR / "company_site", site_name=site_name)
        t0 = time.monotonic()

        raw_jobs = collector.collect(
            city=city, keywords=keywords,
            max_pages_per_keyword=1,
            max_jobs_total=limit // len(sites),
        )

        duration = time.monotonic() - t0
        print(f"{site_name}: {len(raw_jobs)} jobs in {duration:.1f}s")

        if raw_jobs:
            collector.save_raw()
            all_raw.extend(raw_jobs)

    if not all_raw:
        print("无数据。")
        return

    print(f"\n总计: {len(all_raw)} raw jobs")
    # 对所有站点汇总做 pipeline
    _process_combined(all_raw, "company_site", time.monotonic() - t0)


def _process_results(collector, raw_jobs: list, duration: float) -> None:
    """处理采集结果：保存原始数据 → 归一化 → CSV → 质量报告 → 入库。"""
    # 保存 raw JSONL
    jsonl_path = collector.save_raw()

    # 归一化 + CSV
    date_str = time.strftime("%Y-%m-%d")
    csv_path = PROCESSED_DIR / f"jobs_{collector.source_name}_{date_str}.csv"
    count, normalized = pipeline(jsonl_path, csv_path)
    print(f"归一化: {len(raw_jobs)} raw -> {count} normalized -> {csv_path}")

    # 质量报告
    report = generate_quality_report(raw_jobs, normalized, collector.source_name, duration_seconds=duration)
    print_report(report)
    report_path = save_report(report, REPORTS_DIR)
    print(f"质量报告: {report_path}")

    # 入库
    conn = connect(DB_PATH)
    init_db(conn)
    inserted = import_csv(conn, csv_path)
    conn.close()
    print(f"入库: {inserted} 条新记录 -> {DB_PATH}")


def _process_xbrowser_results(
    collector,
    raw_jobs: list,
    duration: float,
    city: str = "",
    keywords: list[str] | None = None,
    start_ts: str = "",
) -> None:
    """处理 xbrowser 采集结果（collector 自带 save_raw）。

    Args:
        collector: Job51XBrowserCollector 实例
        raw_jobs: 采集到的 RawJob 列表
        duration: 采集耗时（秒）
        city: 城市名（用于 crawl_runs 记录）
        keywords: 关键词列表（用于 crawl_runs 记录）
        start_ts: 采集开始时间 ISO 字符串
    """
    # 按城市命名 JSONL 避免多城市覆盖
    safe_city = city.replace("/", "_") if city else "unknown"
    jsonl_path = collector.save_raw(prefix=f"job51_{safe_city}", jobs=raw_jobs)

    date_str = time.strftime("%Y-%m-%d")
    csv_path = PROCESSED_DIR / f"jobs_job51_xbrowser_{date_str}.csv"
    count, normalized = pipeline(jsonl_path, csv_path)
    print(f"归一化: {len(raw_jobs)} raw -> {count} normalized -> {csv_path}")

    report = generate_quality_report(raw_jobs, normalized, "job51_xbrowser", duration_seconds=duration)
    print_report(report)
    report_path = save_report(report, REPORTS_DIR)
    print(f"质量报告: {report_path}")

    conn = connect(DB_PATH)
    init_db(conn)
    stats = import_csv_with_stats(conn, csv_path)
    print(f"入库统计: 新增 {stats.inserted} 条 | 更新 {stats.updated} 条 | 跳过 {stats.skipped} 条 -> {DB_PATH}")

    # 记录采集运行信息
    end_ts = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    record_crawl_run(
        conn,
        source="job51_xbrowser",
        city=city or "未知",
        keywords=keywords or [],
        start_time=start_ts or end_ts,
        end_time=end_ts,
        total_collected=len(raw_jobs),
        new_inserted=stats.inserted,
        updated=stats.updated,
        skipped=stats.skipped,
    )
    conn.close()


def _process_combined(raw_jobs: list, source: str, duration: float) -> None:
    """处理多站点汇总结果。"""
    from src.scraping.pipeline import normalize_batch, write_csv

    date_str = time.strftime("%Y-%m-%d")
    normalized = normalize_batch(raw_jobs)
    csv_path = PROCESSED_DIR / f"jobs_{source}_{date_str}.csv"
    count = write_csv(normalized, csv_path)
    print(f"归一化: {len(raw_jobs)} raw -> {count} normalized -> {csv_path}")

    report = generate_quality_report(raw_jobs, normalized, source, duration_seconds=duration)
    print_report(report)
    save_report(report, REPORTS_DIR)

    conn = connect(DB_PATH)
    init_db(conn)
    inserted = import_csv(conn, csv_path)
    conn.close()
    print(f"入库: {inserted} 条新记录 -> {DB_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="采集入口")
    parser.add_argument("--source", choices=["job51", "job51_xbrowser", "company_site", "all"], default="job51_xbrowser")
    parser.add_argument("--site", default="all", help="企业官网站点名 (meituan/bytedance/tencent/alibaba/all)")
    parser.add_argument("--city", default="成都")
    parser.add_argument("--cities", nargs="+", help="多城市采集（覆盖 --city）")
    parser.add_argument("--keywords", nargs="+", default=DEFAULT_KEYWORDS[:3])
    parser.add_argument("--all-keywords", action="store_true", help="使用全部默认关键词（10 个）")
    parser.add_argument("--limit", type=int, default=100, help="总采集上限")
    parser.add_argument("--limit-per-kw", type=int, default=40, help="每个关键词采集上限")
    parser.add_argument("--enrich-detail", action="store_true", help="访问详情页补充字段（慢）")
    args = parser.parse_args()

    keywords = DEFAULT_KEYWORDS if args.all_keywords else args.keywords
    cities = args.cities if args.cities else [args.city]

    print("=" * 50)
    print(f"采集任务: source={args.source}, cities={cities}, keywords={keywords}")
    print(f"每关键词上限: {args.limit_per_kw}, 总上限: {args.limit}")
    print("=" * 50)

    if args.source in ("job51", "job51_xbrowser"):
        for i, city in enumerate(cities):
            print(f"\n>>> 城市: {city} ({i+1}/{len(cities)})")
            run_job51_xbrowser(city, keywords, min(args.limit_per_kw * len(keywords), args.limit))
            # 城市间添加等待（最后一个城市不等）
            if i < len(cities) - 1:
                wait = city_interval_sleep()
                print(f"城市切换，等待 {wait:.1f}s...")
    elif args.source == "company_site":
        run_company_site(args.city, args.keywords, args.limit, args.site)
    elif args.source == "all":
        print("\n>>> job51")
        run_job51(args.city, args.keywords[:5], args.limit // 2, args.enrich_detail)
        print("\n>>> company_site")
        run_company_site(args.city, args.keywords[:5], args.limit // 2, args.site)


if __name__ == "__main__":
    main()
