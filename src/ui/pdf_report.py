"""PDF 报告导出 — 一键生成当前筛选条件下的分析报告。"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from fpdf import FPDF

# ── 中文字体路径（macOS） ──
_FONT_PATHS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def _find_font() -> Optional[str]:
    for p in _FONT_PATHS:
        if Path(p).exists():
            return p
    return None


class ReportPDF(FPDF):
    """带中文字体的 PDF 报告构建器。"""

    def __init__(self):
        super().__init__("P", "mm", "A4")
        font_path = _find_font()
        if font_path:
            self.add_font("CJK", "", font_path, uni=True)
            self.add_font("CJK", "B", font_path, uni=True)
            self._font = "CJK"
        else:
            self._font = "Helvetica"
        self.set_auto_page_break(True, 20)

    # ── Header / Footer ──
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(self._font, "", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 6, "岗位市场分析报告", align="L")
        self.cell(0, 6, f"第 {self.page_no()} 页", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font(self._font, "", 7)
        self.set_text_color(160, 160, 160)
        self.cell(0, 10, f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  Job Market Analytics", align="C")

    # ── Helpers ──
    def title_page(self, city_str: str, job_count: int):
        """封面。"""
        self.add_page()
        self.ln(60)
        self.set_font(self._font, "B", 28)
        self.set_text_color(0, 100, 148)
        self.cell(0, 14, "岗位市场分析报告", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(8)
        self.set_font(self._font, "", 14)
        self.set_text_color(80, 80, 80)
        self.cell(0, 10, f"数据范围：{city_str}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 10, f"有效岗位：{job_count} 个", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 10, f"报告日期：{datetime.now().strftime('%Y年%m月%d日')}", align="C", new_x="LMARGIN", new_y="NEXT")

    def section_title(self, title: str):
        self.ln(6)
        self.set_font(self._font, "B", 14)
        self.set_text_color(0, 100, 148)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 100, 148)
        self.line(self.l_margin, self.get_y(), self.l_margin + 40, self.get_y())
        self.ln(4)

    def kpi_table(self, metrics: Dict[str, str]):
        self.set_font(self._font, "B", 10)
        self.set_text_color(50, 50, 50)
        col_w = (self.w - self.l_margin - self.r_margin) / len(metrics)
        for label, value in metrics.items():
            self.set_font(self._font, "", 9)
            self.set_text_color(120, 120, 120)
            self.cell(col_w, 6, label, align="C")
            self.set_font(self._font, "B", 13)
            self.set_text_color(0, 100, 148)
            self.cell(col_w, 10, str(value), align="C")
        self.ln(12)

    def simple_table(self, headers: List[str], rows: List[List[str]], col_widths: Optional[List[float]] = None):
        if not col_widths:
            col_widths = [(self.w - self.l_margin - self.r_margin) / len(headers)] * len(headers)

        # Header
        self.set_font(self._font, "B", 9)
        self.set_fill_color(0, 100, 148)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, border=1, fill=True, align="C")
        self.ln()

        # Body
        self.set_font(self._font, "", 8)
        for row in rows:
            self.set_text_color(50, 50, 50)
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 6, str(cell)[:30], border=1, align="C")
            self.ln()

    def paragraph(self, text: str):
        self.set_font(self._font, "", 10)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 6, text)
        self.ln(2)


def generate_report(jobs: pd.DataFrame, city_str: str) -> io.BytesIO:
    """生成 PDF 报告，返回 BytesIO 对象。

    Args:
        jobs: 筛选后的岗位 DataFrame
        city_str: 城市描述文本
    """
    pdf = ReportPDF()
    real = jobs[jobs["salary_avg"].notna()]

    # ── 封面 ──
    pdf.title_page(city_str, len(jobs))

    # ── 1. 核心指标 ──
    pdf.add_page()
    pdf.section_title("一、核心指标")
    metrics = {
        "岗位数": str(len(jobs)),
        "公司数": str(jobs["company_name"].nunique() if "company_name" in jobs.columns else "-"),
        "薪资中位": f"{real['salary_avg'].median():.1f}K" if not real.empty else "-",
        "平均薪资": f"{real['salary_avg'].mean():.1f}K" if not real.empty else "-",
    }
    pdf.kpi_table(metrics)

    # ── 2. 城市对比 ──
    if "city" in jobs.columns and jobs["city"].nunique() > 1:
        pdf.section_title("二、城市对比")
        city_stats = jobs.groupby("city").agg(
            岗位数=("id", "count"),
            平均薪资=("salary_avg", "mean"),
            薪资中位=("salary_avg", "median"),
        ).reset_index()
        city_stats["平均薪资"] = city_stats["平均薪资"].round(1)
        city_stats["薪资中位"] = city_stats["薪资中位"].round(1)
        city_stats = city_stats.sort_values("岗位数", ascending=False)

        rows = []
        for _, r in city_stats.iterrows():
            rows.append([str(r["city"]), str(r["岗位数"]), f"{r['平均薪资']}K", f"{r['薪资中位']}K"])
        pdf.simple_table(["城市", "岗位数", "平均薪资", "薪资中位"], rows,
                         col_widths=[40, 30, 45, 45])

    # ── 3. 热门技能 ──
    if "skills" in jobs.columns:
        pdf.section_title("三、热门技能 TOP10")
        from collections import Counter
        import json

        skill_counter: Counter = Counter()
        for val in jobs["skills"].dropna():
            try:
                items = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                items = [s.strip() for s in str(val).split(",") if s.strip()]
            for s in items:
                skill_counter[str(s).strip()] += 1

        top_skills = skill_counter.most_common(10)
        rows = []
        for sk, cnt in top_skills:
            avg_sal = "-"
            try:
                mask = jobs["skills"].astype(str).str.contains(sk, na=False, regex=False)
                skill_jobs = jobs[mask & jobs["salary_avg"].notna()]
                if not skill_jobs.empty:
                    avg_sal = f"{skill_jobs['salary_avg'].mean():.1f}K"
            except Exception:
                pass
            rows.append([sk, str(cnt), avg_sal])
        pdf.simple_table(["技能", "需求数", "平均薪资"], rows, col_widths=[50, 40, 60])

    # ── 4. 经验分布 ──
    if "experience" in jobs.columns:
        pdf.section_title("四、经验要求分布")
        exp_counts = jobs["experience"].value_counts()
        rows = [[str(k), str(v)] for k, v in exp_counts.items()]
        pdf.simple_table(["经验要求", "岗位数"], rows, col_widths=[80, 80])

    # ── 5. 行业分布 ──
    if "industry" in jobs.columns:
        pdf.section_title("五、行业分布 TOP10")
        ind_counts = jobs["industry"].value_counts().head(10)
        rows = [[str(k), str(v)] for k, v in ind_counts.items()]
        pdf.simple_table(["行业", "岗位数"], rows, col_widths=[80, 80])

    # ── 6. 薪资分位数 ──
    if not real.empty:
        pdf.section_title("六、薪资分位数")
        quantiles = real["salary_avg"].quantile([0.25, 0.5, 0.75, 0.9])
        rows = [
            ["P25 (25%岗位低于此)", f"{quantiles[0.25]:.1f}K"],
            ["P50 (中位数)", f"{quantiles[0.5]:.1f}K"],
            ["P75 (75%岗位低于此)", f"{quantiles[0.75]:.1f}K"],
            ["P90 (高薪门槛)", f"{quantiles[0.9]:.1f}K"],
        ]
        pdf.simple_table(["分位", "月薪"], rows, col_widths=[80, 80])

    # Output
    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf
