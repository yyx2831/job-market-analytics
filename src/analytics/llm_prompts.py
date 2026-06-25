"""LLM 增强 — 生成高质量 Prompt，零 API Key 消耗。

工作流：
  1. 生成 Prompt → 复制到豆包/DeepSeek/其他免费 LLM
  2. 拿到回复 → 贴回仪表盘
  3. 系统解析并展示结果

支持的 Prompt 类型：
  - JD 解读        — 一个岗位JD → 结构化分析（技能要求/薪资解读/公司评估）
  - 岗位对比      — 两个岗位 → 优劣对比 + 推荐
  - 城市选择建议  — 两个城市同一岗位 → 性价比分析
  - 面试准备      — 岗位JD → 面试问题清单 + 准备策略
  - 自定义        — 用户自定义场景
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


# ══════════════════════════════════════════════
#  Prompt 模板
# ══════════════════════════════════════════════

TEMPLATES: Dict[str, Dict] = {
    "jd_analysis": {
        "name": "📋 JD 深度解读",
        "description": "把一个岗位 JD 拆解为结构化信息",
        "prompt_template": """你是一位资深的技术招聘顾问。请分析以下岗位JD，输出结构化信息：

【岗位JD】
{jd_text}

【请按以下格式输出（纯文本，不要 Markdown 表格，每项一行）】

## 岗位概览
职位名称：
核心职责（一句话）：
技术栈（逗号分隔）：
经验要求：
学历要求：
薪资范围：

## 技能清单
必须掌握：
加分项：
加分但非必须：

## 公司信号
公司类型（互联网/传统企业/外企/国企/初创等，根据JD推断）：
技术团队规模信号（如有）：
技术栈成熟度（新兴/成熟/陈旧，根据提及的技术判断）：

## 面试重点
最可能问的技术点（3个）：
软技能侧重点：
准备建议（3条具体建议）：

## 职业发展
这个岗位1-2年后的技术成长空间：
隐性福利信号（如有提到公积金、补贴、弹性工作等）：
推荐指数（1-10，根据JD完整度和吸引力）：
推荐理由（一句话）：""",
    },

    "job_compare": {
        "name": "⚖️ 双岗对比",
        "description": "两个岗位的优劣对比",
        "prompt_template": """你是一位资深的技术招聘顾问。请对比以下两个岗位：

【岗位 A】
{jd_text_a}

【岗位 B】
{jd_text_b}

【请按以下格式输出】

## 综合推荐
推荐选择（A / B / 持平）：
核心理由（2-3句）：

## 维度对比
薪资吸引力：A更强 / B更强 / 持平（说明理由）
技术成长：A更强 / B更强 / 持平（说明理由）
工作生活平衡：A更强 / B更强 / 持平（说明理由）
公司前景：A更强 / B更强 / 持平（说明理由）
团队氛围信号：A更强 / B更强 / 持平（说明理由）

## 风险提示
岗位 A 需要注意的风险：
岗位 B 需要注意的风险：

## 最终建议
如果你更看重技术成长 → 
如果你更看重薪资 → 
如果你更看重稳定性 → """,
    },

    "city_compare": {
        "name": "🌍 城市性价比",
        "description": "两个城市同一岗位的生活成本 vs 薪资分析",
        "prompt_template": """你是一位了解中国各城市生活成本和就业市场的顾问。请比较以下信息：

【对比参数】
岗位类型：{job_type}
城市 A：{city_a}，薪资：{salary_a} 元/月
城市 B：{city_b}，薪资：{salary_b} 元/月
工作年限：{experience}

【请按以下格式输出】

## 薪资面值对比
城市 A 薪资定位（在该城市同岗中的百分位估计）：
城市 B 薪资定位：

## 生活成本估算
城市 A 月均支出估算（住宿+饮食+交通+其他）：
城市 B 月均支出估算：
每月可储蓄金额 A：
每月可储蓄金额 B：

## 实际购买力
扣除生活成本后的「真实」薪资差距：
哪个城市更容易买房/上车：A / B（简要说明）

## 职业发展
该岗位在 A 城的发展前景：
该岗位在 B 城的发展前景：
跳槽机会多寡：A vs B

## 最终建议
性价比更高：A / B
如果考虑长期定居 → 
如果以赚钱为主 → """,
    },

    "interview_prep": {
        "name": "🎯 面试准备清单",
        "description": "根据 JD 生成面试问题和准备策略",
        "prompt_template": """你是一位资深面试官。请根据以下岗位 JD 生成面试准备方案：

【岗位 JD】
{jd_text}

【候选人背景】
技能栈：{candidate_skills}
工作年限：{experience}

【请按以下格式输出】

## 高频技术问题（5个）
1. （问题描述）
2. ...

## 系统设计问题（1-2个，如果是高级岗位）
1. （场景 + 预期讨论要点）

## 行为面试问题（3个）
1. ...
2. ...
3. ...

## 反问建议
可以向面试官提问的 3 个好问题：
1. ...
2. ...
3. ...

## 准备优先级
本周必须掌握：
面试前复习重点：
可以战略性放弃的：

## 面试当天 Checklist
- [ ] ...
- [ ] ...
- [ ] ...""",
    },

    "custom": {
        "name": "✨ 自定义",
        "description": "自由定义 Prompt 场景",
        "prompt_template": "{custom_prompt}",
    },
}


# ══════════════════════════════════════════════
#  核心类
# ══════════════════════════════════════════════

@dataclass
class PromptResult:
    id: str
    template: str
    prompt: str
    response: str = ""
    created_at: str = ""
    parsed: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class PromptEngine:
    """Prompt 生成引擎。

    用法:
        engine = PromptEngine()
        prompt = engine.generate("jd_analysis", jd_text="...")
        # → 用户复制 prompt 到豆包/DeepSeek
        # → 用户把回复贴回来
        result = engine.ingest_response(prompt, response_text)
    """

    def __init__(self):
        pass

    def list_templates(self) -> List[Dict]:
        """列出所有可用模板。"""
        return [
            {"id": tid, "name": t["name"], "description": t["description"]}
            for tid, t in TEMPLATES.items()
        ]

    def generate(self, template_id: str, **kwargs) -> PromptResult:
        """根据模板生成 Prompt。

        Args:
            template_id: 模板 ID
            **kwargs: 模板变量（jd_text, city_a, salary_a 等）
        """
        if template_id not in TEMPLATES:
            raise ValueError(f"未知模板: {template_id}，可选: {list(TEMPLATES.keys())}")

        t = TEMPLATES[template_id]
        prompt_text = t["prompt_template"].format(**kwargs)

        return PromptResult(
            id=str(uuid.uuid4())[:8],
            template=template_id,
            prompt=prompt_text,
        )

    def ingest_response(self, result: PromptResult, response_text: str) -> PromptResult:
        """注入 LLM 回复。"""
        result.response = response_text
        return result

    @staticmethod
    def get_template_variables(template_id: str) -> List[str]:
        """获取模板需要的变量列表。"""
        if template_id not in TEMPLATES:
            return []
        import re
        text = TEMPLATES[template_id]["prompt_template"]
        return list(set(re.findall(r"\{(\w+)\}", text)))


# ══════════════════════════════════════════════
#  批量 JD 总结（不走 API）
# ══════════════════════════════════════════════

def batch_jd_summary_prompts(
    jobs_df, n: int = 5, by_city: str = ""
) -> List[PromptResult]:
    """批量生成 JD 解读 Prompt（一次复制多个）。"""
    engine = PromptEngine()
    results = []

    df = jobs_df.copy()
    if by_city:
        df = df[df["city"] == by_city]

    df = df.dropna(subset=["description"])
    if "salary_avg" in df.columns:
        df = df.sort_values("salary_avg", ascending=False)

    for _, row in df.head(n).iterrows():
        jd = row.get("description", "")
        title = row.get("title", "未知岗位")
        company = row.get("company_name", "")

        # 构建增强 JD 文本
        jd_text = f"职位：{title}\n公司：{company}\n"
        if pd.notna(row.get("salary_text")):
            jd_text += f"薪资：{row['salary_text']}\n"
        jd_text += f"\n{jd}"

        pr = engine.generate("jd_analysis", jd_text=jd_text[:3000])
        results.append(pr)

    return results


import pandas as pd
