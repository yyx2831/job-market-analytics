"""薪资文本增强解析器 — 补全中文格式解析 + 年薪换算。

支持格式：
  - 标准: "10-20K·14薪", "10-20K", "1-2万", "8千-1.2万", "4-6千"
  - 年薪: "15-25万/年", "20-30万/年"
  - 额外薪数: "·13薪", "·14薪", "13-16薪", "年底双薪", "年终奖2-4月"

输出:
  - salary_monthly: 归一化月薪(元)
  - salary_months_parsed: 解析出的年薪月数
  - salary_annual: 年薪 = monthly × months
  - is_annual_text: 原始文本是否为年薪格式
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ParsedSalary:
    salary_min: Optional[float] = None       # 月薪下限(元)
    salary_max: Optional[float] = None       # 月薪上限(元)
    salary_avg: Optional[float] = None       # 月薪均值(元)
    months: int = 12                         # 年薪月数
    annual_min: Optional[float] = None       # 年薪下限
    annual_max: Optional[float] = None       # 年薪上限
    annual_avg: Optional[float] = None       # 年薪均值
    is_annual_format: bool = False           # 原始是否为年薪格式
    raw_text: str = ""


# ── 匹配模式 ──

# 千元: "4-6千", "4.5-9千", "8千-1.2万"
_RE_QIAN = re.compile(r"(\d+\.?\d*)\s*[千k][-~至到]\s*(\d+\.?\d*)\s*千")
_RE_QIAN_WAN = re.compile(r"(\d+\.?\d*)\s*千[-~至到]\s*(\d+\.?\d*)\s*万")
_RE_WAN = re.compile(r"(\d+\.?\d*)\s*万[-~至到]\s*(\d+\.?\d*)\s*万")
_RE_SINGLE_QIAN = re.compile(r"(\d+\.?\d*)\s*千")
_RE_SINGLE_WAN = re.compile(r"(\d+\.?\d*)\s*万")

# 标准 K 格式: "10-20K", "15-30K"
_RE_K = re.compile(r"(\d+\.?\d*)\s*[-~至到]\s*(\d+\.?\d*)\s*[kK]")

# 年薪格式: "15-20万/年", "20-30万/年", "1-2万/年"
_RE_ANNUAL_WAN = re.compile(r"(\d+\.?\d*)\s*[-~至到]\s*(\d+\.?\d*)\s*万\s*(/\s*年)?")
_RE_ANNUAL_SINGLE = re.compile(r"(\d+\.?\d*)\s*万以下\s*(/\s*年)?")
_RE_ANNUAL_ABOVE = re.compile(r"(\d+\.?\d*)\s*万以上\s*(/\s*年)?")

# 额外薪数: "·13薪", "·14薪", "13-16薪", "年底双薪"
_RE_MONTHS_DOT = re.compile(r"[·×\*xX]\s*(\d+)\s*薪")
_RE_MONTHS_RANGE = re.compile(r"(\d+)\s*[-~至到]\s*(\d+)\s*薪")
_RE_DOUBLE_SALARY = re.compile(r"年底双薪|年终双薪|双薪")
_RE_BONUS_MONTHS = re.compile(r"年终奖?\s*(\d+)\s*[-~至到]?\s*(\d*)\s*(个?月|薪)?")

# 面议 / 无
_RE_NEGOTIABLE = re.compile(r"面议|面談|面談|薪资面议|待遇面议")


def _parse_chinese_salary(text: str) -> Optional[Tuple[float, float]]:
    """解析中文薪资文本，返回 (min_monthly, max_monthly) 元/月。"""
    text = text.strip().lower().replace(" ", "").replace("k", "千").replace("K", "千")

    # "4-6千"
    m = _RE_QIAN.search(text)
    if m:
        return float(m.group(1)) * 1000, float(m.group(2)) * 1000

    # "8千-1.2万"
    m = _RE_QIAN_WAN.search(text)
    if m:
        return float(m.group(1)) * 1000, float(m.group(2)) * 10000

    # "1-2万" (2万 for two items)
    m = _RE_WAN.search(text)
    if m:
        return float(m.group(1)) * 10000, float(m.group(2)) * 10000

    # 单值: "4千", "1.5万"
    m = _RE_SINGLE_WAN.search(text)
    if m:
        val = float(m.group(1)) * 10000
        return val, val
    m = _RE_SINGLE_QIAN.search(text)
    if m:
        val = float(m.group(1)) * 1000
        return val, val

    # "10-20K"
    m = _RE_K.search(text)
    if m:
        return float(m.group(1)) * 1000, float(m.group(2)) * 1000

    return None


def _parse_annual_salary(text: str) -> Optional[Tuple[float, float]]:
    """解析年薪文本，返回 (min_annual, max_annual) 元/年。"""
    text = text.strip().lower().replace(" ", "").replace("k", "千").replace("K", "千")

    # "15-20万/年"
    m = _RE_ANNUAL_WAN.search(text)
    if m:
        return float(m.group(1)) * 10000, float(m.group(2)) * 10000

    # "3万及以下/年" — just use the bound
    m = _RE_ANNUAL_SINGLE.search(text)
    if m:
        val = float(m.group(1)) * 10000
        return val, val

    # "50万以上/年"
    m = _RE_ANNUAL_ABOVE.search(text)
    if m:
        val = float(m.group(1)) * 10000
        return val, val

    return None


def _parse_salary_months(text: str) -> int:
    """从文本提取年薪月数。"""
    # "·13薪" / "·14薪"
    m = _RE_MONTHS_DOT.search(text)
    if m:
        return int(m.group(1))

    # "13-16薪" — 取均值
    m = _RE_MONTHS_RANGE.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo + hi) // 2

    # 年底双薪 → 13薪
    if _RE_DOUBLE_SALARY.search(text):
        return 13

    # "年终奖2-4个月" → 12 + avg
    m = _RE_BONUS_MONTHS.search(text)
    if m:
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        return 12 + (lo + hi) // 2

    return 12


def parse_salary(text: Optional[str]) -> ParsedSalary:
    """全面解析薪资文本。

    Args:
        text: 原始薪资字符串，如 "10-20K·14薪", "1-2万/月", "15-20万/年"

    Returns:
        ParsedSalary with all computed fields.
    """
    result = ParsedSalary(raw_text=text or "")

    if not text or _RE_NEGOTIABLE.search(text):
        return result

    text_clean = text.strip()

    # ── Step 1: 检查是否为年薪格式 ──
    annual = _parse_annual_salary(text_clean)
    if annual is not None:
        result.salary_min = annual[0] / 12  # 折月薪
        result.salary_max = annual[1] / 12
        result.salary_avg = (result.salary_min + result.salary_max) / 2
        result.months = 12
        result.annual_min = annual[0]
        result.annual_max = annual[1]
        result.annual_avg = (annual[0] + annual[1]) / 2
        result.is_annual_format = True
        return result

    # ── Step 2: 解析月薪金额 ──
    monthly = _parse_chinese_salary(text_clean)
    if monthly is None:
        return result

    result.salary_min = monthly[0]
    result.salary_max = monthly[1]
    result.salary_avg = (monthly[0] + monthly[1]) / 2

    # ── Step 3: 解析年薪月数 ──
    result.months = _parse_salary_months(text_clean)

    # ── Step 4: 计算年薪 ──
    result.annual_min = result.salary_min * result.months
    result.annual_max = result.salary_max * result.months
    result.annual_avg = result.salary_avg * result.months

    return result


def enhance_salary_columns(dataframe: "pd.DataFrame") -> "pd.DataFrame":
    """对 DataFrame 中每条记录重新解析薪资，回填缺失字段。

    新增列:
      - salary_annual: 年薪(元)
      - salary_monthly_equiv: 折12薪月薪(用于公平跨薪数对比)
    """
    import pandas as pd

    df = dataframe.copy()

    new_min = []
    new_max = []
    new_avg = []
    new_months = []
    new_annual = []

    for _, row in df.iterrows():
        text = row.get("salary_text")
        parsed = parse_salary(text)

        # 保留原有值或使用解析值
        mn = row.get("salary_min")
        mx = row.get("salary_max")
        av = row.get("salary_avg")

        if parsed.salary_min is not None:
            # 年薪格式 → 用解析月薪
            if parsed.is_annual_format:
                mn = parsed.salary_min
                mx = parsed.salary_max
                av = parsed.salary_avg
            elif mn is None or (pd.isna(mn) if hasattr(mn, '__iter__') is False else False):
                # 原本为 NULL → 用解析值
                mn = parsed.salary_min
                mx = parsed.salary_max
                av = parsed.salary_avg

        new_min.append(mn)
        new_max.append(mx)
        new_avg.append(av)

        # months: 优先用已解析的(>=12)，否则用新的
        existing_months = row.get("salary_months")
        if pd.notna(existing_months) and existing_months >= 12:
            new_months.append(int(existing_months))
        else:
            new_months.append(parsed.months)

        # 年薪
        if av is not None and not (isinstance(av, float) and pd.isna(av)):
            new_annual.append(av * new_months[-1])
        else:
            new_annual.append(None)

    df["salary_min"] = new_min
    df["salary_max"] = new_max
    df["salary_avg"] = new_avg
    df["salary_months"] = new_months
    df["salary_annual"] = new_annual

    # 折12薪月薪 = 年薪 / 12，用于跨薪数公平对比
    df["salary_monthly_equiv"] = df["salary_annual"] / 12

    return df


def months_distribution(dataframe: "pd.DataFrame") -> dict:
    """统计薪资月数分布。"""
    dist = dataframe["salary_months"].value_counts().to_dict()
    # 分组: 12薪 / 13薪 / 14薪 / 15薪 / 16+薪
    grouped = {"12薪": 0, "13薪": 0, "14薪": 0, "15薪": 0, "16+薪": 0}
    for months, cnt in dist.items():
        if months == 12:
            grouped["12薪"] += cnt
        elif months == 13:
            grouped["13薪"] += cnt
        elif months == 14:
            grouped["14薪"] += cnt
        elif months == 15:
            grouped["15薪"] += cnt
        elif months >= 16:
            grouped["16+薪"] += cnt
    return grouped


def fourteen_month_analysis(dataframe: "pd.DataFrame") -> dict:
    """14薪对比分析 — 返回 12薪 vs 13+薪的薪酬差异维度。"""
    df = dataframe.dropna(subset=["salary_avg", "salary_months"])

    salary_12m = df[df["salary_months"] == 12]["salary_avg"]
    salary_13p = df[df["salary_months"] > 12]["salary_avg"]

    result = {
        "cnt_12m": len(salary_12m),
        "cnt_13p": len(salary_13p),
        "avg_12m": round(salary_12m.mean(), 0) if not salary_12m.empty else 0,
        "avg_13p": round(salary_13p.mean(), 0) if not salary_13p.empty else 0,
        "med_12m": round(salary_12m.median(), 0) if not salary_12m.empty else 0,
        "med_13p": round(salary_13p.median(), 0) if not salary_13p.empty else 0,
    }

    # 按城市分组
    if "city" in df.columns:
        city_stats = []
        for city in df["city"].dropna().unique():
            cd = df[df["city"] == city]
            c12 = cd[cd["salary_months"] == 12]["salary_avg"]
            c13 = cd[cd["salary_months"] > 12]["salary_avg"]
            if len(c12) >= 5 and len(c13) >= 3:
                city_stats.append({
                    "城市": city,
                    "12薪均薪": round(c12.mean(), 0),
                    "13+薪均薪": round(c13.mean(), 0),
                    "16薪溢价": round((c13.mean() / c12.mean() - 1) * 100, 1) if c12.mean() > 0 else 0,
                    "12薪数量": len(c12),
                    "13+薪数量": len(c13),
                })
        result["by_city"] = city_stats

    return result
