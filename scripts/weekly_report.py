#!/usr/bin/env python3
"""
成都市场周报生成器 — Markdown 格式。

包含：
- 本周新增岗位数
- 薪资变动（对比上周）
- 热门技能 TOP10
- 高薪岗位 TOP5
- AI/AI相关岗位占比变化

用法:
  python3 scripts/weekly_report.py
  python3 scripts/weekly_report.py --send-email your@email.com
  python3 scripts/weekly_report.py --city 成都
  python3 scripts/weekly_report.py --city 成都 --output reports/weekly.md
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(__file__).parent.parent / "data" / "processed" / "jobs.db"
REPORTS_DIR = Path(__file__).parent.parent / "reports"

AI_KEYWORDS = [
    "AI", "人工智能", "机器学习", "深度学习", "大模型", "LLM",
    "NLP", "自然语言", "计算机视觉", "CV", "推荐算法",
    "数据挖掘", "算法工程师", "AIGC", "智能", "GPT",
]


def parse_skills(val) -> list:
    """Parse skills field into list."""
    if pd.isna(val):
        return []
    if isinstance(val, list):
        return [str(s).strip() for s in val]
    try:
        items = json.loads(val)
    except (json.JSONDecodeError, TypeError):
        items = [s.strip() for s in str(val).split(",") if s.strip()]
    return [str(s).strip() for s in items]


def is_ai_related(row) -> bool:
    """Check if a job is AI-related by title, skills, or industry."""
    text = (
        str(row.get("title", "")) + " "
        + str(row.get("skills", "")) + " "
        + str(row.get("industry", ""))
    ).lower()
    for kw in AI_KEYWORDS:
        if kw.lower() in text:
            return True
    return False


def format_salary(val):
    """Format salary as readable string."""
    if val is None or val == 0:
        return "面议"
    if val >= 10000:
        return f"¥{val/10000:.1f}万/月"
    return f"¥{int(val)}/月"


def generate_weekly_report(
    city: str = "成都",
    db_path: Path = DB_PATH,
) -> str:
    """Generate Markdown weekly report for a given city."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start

    # Load all jobs
    jobs_all = pd.read_sql("SELECT * FROM jobs", conn)

    # ── Filter by city ──
    if city:
        city_jobs = jobs_all[jobs_all["city"] == city].copy()
    else:
        city_jobs = jobs_all.copy()

    # ── Time-based split: use created_at for "本周" vs "上周" ──
    city_jobs["_created_dt"] = pd.to_datetime(
        city_jobs["created_at"].str[:19], errors="coerce"
    )

    this_week = city_jobs[
        city_jobs["_created_dt"] >= pd.Timestamp(week_start)
    ].copy()
    last_week = city_jobs[
        (city_jobs["_created_dt"] >= pd.Timestamp(prev_week_start))
        & (city_jobs["_created_dt"] < pd.Timestamp(prev_week_end))
    ].copy()

    # Fallback: if no data this week by created_at, use collection_batch
    if len(this_week) == 0:
        batches = city_jobs["collection_batch"].dropna().unique()
        if len(batches) >= 2:
            latest_batch = sorted(batches)[-1]
            second_batch = sorted(batches)[-2]
            this_week = city_jobs[city_jobs["collection_batch"] == latest_batch].copy()
            last_week = city_jobs[city_jobs["collection_batch"] == second_batch].copy()
            week_label = f"最新采集批次 ({latest_batch})"
            prev_label = f"前一采集批次 ({second_batch})"
        else:
            # Single batch: use all data as "this period", compare with "before"
            mid_idx = len(city_jobs) // 2
            this_week = city_jobs.iloc[mid_idx:].copy()
            last_week = city_jobs.iloc[:mid_idx].copy()
            week_label = "最近半批"
            prev_label = "前半批"
    else:
        week_label = f"本周 ({week_start.strftime('%m/%d')} - {now.strftime('%m/%d')})"
        prev_label = f"上周 ({prev_week_start.strftime('%m/%d')} - {prev_week_end.strftime('%m/%d')})"

    # ── 构建报告 ──
    lines = []
    lines.append(f"# 📊 {city}岗位市场周报")
    lines.append(f"\n**生成时间**: {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"\n**数据来源**: {db_path.name} ({len(city_jobs)} 条 {city} 岗位)")
    lines.append("\n---")

    # ── 1. 本周新增岗位数 ──
    lines.append(f"\n## 📈 一、新增岗位数")
    lines.append(f"\n| 指标 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| {week_label} 岗位数 | {len(this_week)} |")
    lines.append(f"| {prev_label} 岗位数 | {len(last_week)} |")
    if len(last_week) > 0:
        change_pct = (len(this_week) - len(last_week)) / len(last_week) * 100
        change_icon = "📈" if change_pct > 0 else ("📉" if change_pct < 0 else "➡️")
        lines.append(f"| 环比变化 | {change_icon} {change_pct:+.1f}% |")
    lines.append(f"| {city} 累计岗位总数 | {len(city_jobs)} |")

    # ── 2. 薪资变动 ──
    lines.append(f"\n## 💰 二、薪资变动")
    this_sal = this_week["salary_avg"].replace(0, np.nan).dropna()
    last_sal = last_week["salary_avg"].replace(0, np.nan).dropna()

    lines.append(f"\n| 指标 | {week_label} | {prev_label} | 变化 |")
    lines.append(f"|------|-------------|-------------|------|")
    if len(this_sal) > 0 and len(last_sal) > 0:
        avg_this = this_sal.mean()
        avg_last = last_sal.mean()
        med_this = this_sal.median()
        med_last = last_sal.median()
        p25_this = this_sal.quantile(0.25)
        p25_last = last_sal.quantile(0.25)
        p75_this = this_sal.quantile(0.75)
        p75_last = last_sal.quantile(0.75)

        lines.append(f"| 平均月薪 | {format_salary(avg_this)} | {format_salary(avg_last)} | {avg_this-avg_last:+,.0f} |")
        lines.append(f"| 中位数月薪 | {format_salary(med_this)} | {format_salary(med_last)} | {med_this-med_last:+,.0f} |")
        lines.append(f"| P25 | {format_salary(p25_this)} | {format_salary(p25_last)} | {p25_this-p25_last:+,.0f} |")
        lines.append(f"| P75 | {format_salary(p75_this)} | {format_salary(p75_last)} | {p75_this-p75_last:+,.0f} |")
    else:
        lines.append(f"| (薪资数据不足) | - | - | - |")

    # ── 3. 热门技能 TOP10 ──
    lines.append(f"\n## 🔥 三、热门技能 TOP10")

    skill_counter = Counter()
    for _, row in city_jobs.iterrows():
        for s in parse_skills(row.get("skills")):
            if s and len(s) > 1:
                skill_counter[s] += 1

    skill_counter_this = Counter()
    for _, row in this_week.iterrows():
        for s in parse_skills(row.get("skills")):
            if s and len(s) > 1:
                skill_counter_this[s] += 1

    lines.append(f"\n| 排名 | 技能 | 全量需求 | 本期需求 | 趋势 |")
    lines.append(f"|------|------|----------|----------|------|")
    rank = 0
    for skill, count in skill_counter.most_common(20):
        rank += 1
        this_count = skill_counter_this.get(skill, 0)
        if rank <= 10:
            # 简化趋势：本期>全量平均 → 上升趋势
            if len(last_week) > 0 and this_count > 0:
                expected = count * len(this_week) / len(city_jobs)
                trend = "📈 上升" if this_count > expected else ("📉 下降" if this_count < expected * 0.8 else "➡️ 持平")
            else:
                trend = "—"
            lines.append(f"| {rank} | {skill} | {count} | {this_count} | {trend} |")
        else:
            lines.append(f"| {rank} | {skill} | {count} | {this_count} | |")

    # ── 4. 高薪岗位 TOP5 ──
    lines.append(f"\n## 💎 四、高薪岗位 TOP5")

    high_salary = city_jobs[city_jobs["salary_avg"] > 0].nlargest(5, "salary_avg")
    lines.append(f"\n| 排名 | 岗位名称 | 公司 | 月薪 | 行业 |")
    lines.append(f"|------|----------|------|------|------|")
    for i, (_, row) in enumerate(high_salary.iterrows()):
        lines.append(
            f"| {i+1} | {row['title']} | {row['company_name']} | "
            f"{format_salary(row['salary_avg'])} | {row.get('industry', '-')} |"
        )

    # ── 5. AI/AI相关岗位占比变化 ──
    lines.append(f"\n## 🤖 五、AI 相关岗位分析")

    city_jobs["_is_ai"] = city_jobs.apply(is_ai_related, axis=1)
    this_week["_is_ai"] = this_week.apply(is_ai_related, axis=1) if len(this_week) > 0 else pd.Series(dtype=bool)
    last_week["_is_ai"] = last_week.apply(is_ai_related, axis=1) if len(last_week) > 0 else pd.Series(dtype=bool)

    ai_all = city_jobs["_is_ai"].sum()
    ai_all_pct = ai_all / len(city_jobs) * 100 if len(city_jobs) > 0 else 0
    ai_this = this_week["_is_ai"].sum() if len(this_week) > 0 else 0
    ai_this_pct = ai_this / len(this_week) * 100 if len(this_week) > 0 else 0
    ai_last = last_week["_is_ai"].sum() if len(last_week) > 0 else 0
    ai_last_pct = ai_last / len(last_week) * 100 if len(last_week) > 0 else 0

    lines.append(f"\n| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| AI相关岗位总数 ({city}) | {ai_all} |")
    lines.append(f"| AI相关占比 | {ai_all_pct:.1f}% |")
    lines.append(f"| {week_label} AI岗位数 | {ai_this} ({ai_this_pct:.1f}%) |")
    lines.append(f"| {prev_label} AI岗位数 | {ai_last} ({ai_last_pct:.1f}%) |")
    if ai_last_pct > 0:
        change = ai_this_pct - ai_last_pct
        change_icon = "📈" if change > 0 else ("📉" if change < 0 else "➡️")
        lines.append(f"| AI占比变化 | {change_icon} {change:+.1f} 百分点 |")

    # ── AI岗位薪资对比 ──
    ai_jobs = city_jobs[city_jobs["_is_ai"] & (city_jobs["salary_avg"] > 0)]
    non_ai_jobs = city_jobs[~city_jobs["_is_ai"] & (city_jobs["salary_avg"] > 0)]
    if len(ai_jobs) > 0 and len(non_ai_jobs) > 0:
        lines.append(f"\n| 类别 | 平均月薪 | 中位数月薪 | 岗位数 |")
        lines.append(f"|------|----------|------------|--------|")
        lines.append(f"| AI相关 | {format_salary(ai_jobs['salary_avg'].mean())} | {format_salary(ai_jobs['salary_avg'].median())} | {len(ai_jobs)} |")
        lines.append(f"| 非AI | {format_salary(non_ai_jobs['salary_avg'].mean())} | {format_salary(non_ai_jobs['salary_avg'].median())} | {len(non_ai_jobs)} |")
        premium = (ai_jobs["salary_avg"].mean() - non_ai_jobs["salary_avg"].mean()) / non_ai_jobs["salary_avg"].mean() * 100
        lines.append(f"| AI薪资溢价 | +{premium:.1f}% | — | — |")

    lines.append(f"\n---")
    lines.append(f"\n*报告由 Job Market Analytics 自动生成*")

    report = "\n".join(lines)

    # Clean up temp columns
    if "_is_ai" in city_jobs.columns:
        city_jobs.drop(columns=["_is_ai"], inplace=True)

    conn.close()
    return report


def send_email_via_sendmail(to_email: str, subject: str, body: str, sender: str = "report@job-market.local"):
    """Send email using system sendmail."""
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    # Also attach plain text
    plain_body = body.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n")
    text_part = MIMEText(plain_body, "plain")
    msg.attach(text_part)

    try:
        p = subprocess.Popen(
            ["/usr/sbin/sendmail", "-t", "-oi"],
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate(msg.as_bytes())
        if p.returncode != 0:
            print(f"sendmail error: {stderr.decode() if stderr else 'unknown'}", file=sys.stderr)
            return False
        print(f"✅ 邮件已发送至 {to_email}")
        return True
    except FileNotFoundError:
        # sendmail not available, try SMTP
        print("⚠️  sendmail 不可用，尝试使用 SMTP...", file=sys.stderr)
        return _send_via_smtp(to_email, subject, body, sender)


def _send_via_smtp(to_email: str, subject: str, body: str, sender: str = "report@job-market.local") -> bool:
    """Fallback: send via localhost SMTP."""
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    html_part = MIMEText(body, "html")
    text_part = MIMEText(body.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n"), "plain")
    msg.attach(text_part)
    msg.attach(html_part)

    try:
        with smtplib.SMTP("localhost", 25, timeout=10) as server:
            server.send_message(msg)
        print(f"✅ 邮件已通过 SMTP 发送至 {to_email}")
        return True
    except Exception as e:
        print(f"❌ SMTP 发送失败: {e}", file=sys.stderr)
        return False


def md_to_html(md_text: str) -> str:
    """Simple Markdown-to-HTML conversion for email body."""
    import re

    html = md_text

    # Headers
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)

    # Table: convert markdown table rows to HTML
    lines = html.split("\n")
    result = []
    in_table = False
    table_rows = []

    for line in lines:
        if line.startswith("|") and line.endswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            if re.match(r"^\|[\s\-:]+\|", line):
                # Separator row, skip
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            table_rows.append(cells)
        else:
            if in_table:
                # End table, render it
                html_table = "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>\n"
                for i, row in enumerate(table_rows):
                    tag = "th" if i == 0 else "td"
                    html_table += "<tr>"
                    for cell in row:
                        html_table += f"<{tag}>{cell}</{tag}>"
                    html_table += "</tr>\n"
                html_table += "</table>\n"
                result.append(html_table)
                in_table = False
                table_rows = []
            # Bold
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            # Italic
            line = re.sub(r"\*(.+?)\*", r"<em>\1</em>", line)
            # HR
            line = re.sub(r"^---+$", "<hr>", line)
            result.append(line)

    if in_table and table_rows:
        html_table = "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>\n"
        for i, row in enumerate(table_rows):
            tag = "th" if i == 0 else "td"
            html_table += "<tr>"
            for cell in row:
                html_table += f"<{tag}>{cell}</{tag}>"
            html_table += "</tr>\n"
        html_table += "</table>\n"
        result.append(html_table)

    body = "<br>\n".join(result)
    return f"""<html>
<head><meta charset="utf-8"><style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
  h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
  h2 {{ color: #2980b9; margin-top: 30px; }}
  table {{ width: 100%; margin: 10px 0; }}
  th {{ background-color: #3498db; color: white; }}
  tr:nth-child(even) {{ background-color: #f2f2f2; }}
  hr {{ border: 1px solid #ddd; }}
</style></head>
<body>
{body}
</body></html>"""


def main():
    parser = argparse.ArgumentParser(description="生成岗位市场周报")
    parser.add_argument("--city", default="成都", help="目标城市 (默认: 成都)")
    parser.add_argument("--output", "-o", help="输出文件路径 (默认: reports/weekly_YYYYMMDD.md)")
    parser.add_argument("--send-email", metavar="EMAIL", help="发送周报到指定邮箱")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite 数据库路径")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}", file=sys.stderr)
        sys.exit(1)

    # Generate report
    print(f"📊 正在生成 {args.city} 市场周报...")
    report_md = generate_weekly_report(city=args.city, db_path=db_path)

    # Determine output path
    today = datetime.now().strftime("%Y%m%d")
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = REPORTS_DIR / f"weekly_{today}.md"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"✅ 周报已保存至: {out_path}")

    # Send email if requested
    if args.send_email:
        html_body = md_to_html(report_md)
        subject = f"📊 {args.city}岗位市场周报 - {today}"
        send_email_via_sendmail(args.send_email, subject, html_body)

    # Print summary
    print(report_md)


if __name__ == "__main__":
    main()
