"""LLM 增强标签页 — 生成 Prompt → 复制到免费 LLM → 贴回结果。"""

from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st


def render_llm_prompts(jobs: pd.DataFrame) -> None:
    """渲染 LLM 增强标签页。"""
    from src.analytics.llm_prompts import (
        PromptEngine, TEMPLATES, batch_jd_summary_prompts,
    )

    st.subheader("🤖 LLM 智能分析")
    st.caption("生成高质量 Prompt → 复制到豆包/DeepSeek → 贴回结果（零 API Key 消耗）")

    engine = PromptEngine()

    # ── 模式选择 ──
    mode = st.radio(
        "选择模式",
        ["📋 单岗位 JD 解读", "⚖️ 双岗对比", "🌍 城市对比", "🎯 面试准备", "📦 批量 JD 分析", "✨ 自定义"],
        horizontal=True,
    )

    prompt = None

    # ═══════════════════════════════════
    #  模式 1: JD 解读
    # ═══════════════════════════════════
    if mode == "📋 单岗位 JD 解读":
        # 先选岗位
        selected = _job_selector(jobs)
        if selected is not None:
            jd_text = _build_jd_text(selected)

            with st.form("jd_form"):
                st.text_area("JD 内容（可编辑）", jd_text, height=200, key="jd_text")
                submitted = st.form_submit_button("🔮 生成分析 Prompt", use_container_width=True)

            if submitted:
                prompt = engine.generate("jd_analysis", jd_text=st.session_state.get("jd_text", jd_text))

    # ═══════════════════════════════════
    #  模式 2: 双岗对比
    # ═══════════════════════════════════
    elif mode == "⚖️ 双岗对比":
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**岗位 A**")
            job_a = _job_selector(jobs, key_prefix="cmp_a")
        with col_b:
            st.markdown("**岗位 B**")
            job_b = _job_selector(jobs, key_prefix="cmp_b")

        if job_a is not None and job_b is not None:
            if st.button("🔮 生成对比 Prompt", use_container_width=True):
                prompt = engine.generate(
                    "job_compare",
                    jd_text_a=_build_jd_text(job_a),
                    jd_text_b=_build_jd_text(job_b),
                )

    # ═══════════════════════════════════
    #  模式 3: 城市对比
    # ═══════════════════════════════════
    elif mode == "🌍 城市对比":
        cities = sorted(jobs["city"].dropna().unique().tolist())
        with st.form("city_form"):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                city_a = st.selectbox("城市 A", cities, index=0)
                salary_a = st.number_input("城市 A 月薪(元)", value=15000, step=1000)
            with col_b:
                city_b = st.selectbox("城市 B", cities, index=min(1, len(cities) - 1))
                salary_b = st.number_input("城市 B 月薪(元)", value=20000, step=1000)
            with col_c:
                job_type = st.text_input("岗位类型", value="Python 后端开发")
                experience = st.selectbox(
                    "工作年限", ["应届生", "1-3年", "3-5年", "5-10年", "10年以上"], index=1
                )
            submitted = st.form_submit_button("🔮 生成城市对比 Prompt")

        if submitted:
            prompt = engine.generate(
                "city_compare",
                job_type=job_type,
                city_a=city_a, salary_a=f"{salary_a:,}",
                city_b=city_b, salary_b=f"{salary_b:,}",
                experience=experience,
            )

    # ═══════════════════════════════════
    #  模式 4: 面试准备
    # ═══════════════════════════════════
    elif mode == "🎯 面试准备":
        selected = _job_selector(jobs)
        if selected is not None:
            with st.form("interview_form"):
                st.text_area("JD 内容（可编辑）", _build_jd_text(selected), height=150, key="int_jd")
                col_s, col_e = st.columns(2)
                with col_s:
                    candidate_skills = st.text_input(
                        "你的技能栈（逗号分隔）", value="Python, MySQL, Docker"
                    )
                with col_e:
                    experience = st.selectbox(
                        "工作年限", ["应届生", "1-3年", "3-5年", "5-10年", "10年以上"], index=2
                    )
                submitted = st.form_submit_button("🔮 生成面试准备 Prompt")

            if submitted:
                prompt = engine.generate(
                    "interview_prep",
                    jd_text=st.session_state.get("int_jd", _build_jd_text(selected)),
                    candidate_skills=candidate_skills,
                    experience=experience,
                )

    # ═══════════════════════════════════
    #  模式 5: 批量 JD
    # ═══════════════════════════════════
    elif mode == "📦 批量 JD 分析":
        st.markdown("### 批量生成 JD 解读 Prompt")
        col_c, col_n = st.columns(2)
        with col_c:
            city_filter = st.selectbox(
                "限定城市（可选）", ["全部"] + sorted(jobs["city"].dropna().unique().tolist())
            )
        with col_n:
            n_jobs = st.slider("数量", 1, 10, 3)

        if st.button("🔮 批量生成", use_container_width=True):
            city = city_filter if city_filter != "全部" else ""
            results = batch_jd_summary_prompts(jobs, n=n_jobs, by_city=city)

            st.markdown("---")
            st.success(f"已生成 {len(results)} 个 Prompt")

            for i, pr in enumerate(results):
                with st.expander(f"📋 岗位 {i+1} - Prompt ({len(pr.prompt)} chars)"):
                    st.code(pr.prompt, language="markdown")
                    st.download_button(
                        f"📥 下载 Prompt {i+1}",
                        pr.prompt,
                        file_name=f"jd_prompt_{i+1}.md",
                        mime="text/markdown",
                        key=f"dl_{i}",
                    )

    # ═══════════════════════════════════
    #  模式 6: 自定义
    # ═══════════════════════════════════
    elif mode == "✨ 自定义":
        st.markdown("### 自定义场景")
        templates = engine.list_templates()
        template_id = st.selectbox(
            "基于模板（可选）",
            ["无模板"] + [t["name"] for t in templates],
        )

        with st.form("custom_form"):
            custom_text = st.text_area(
                "你的 Prompt",
                height=200,
                placeholder="描述你需要分析的内容...",
            )
            submitted = st.form_submit_button("🔮 生成")

        if submitted and custom_text:
            tid = next(
                (t["id"] for t in templates if t["name"] == template_id), None
            )
            if tid and tid != "custom":
                prompt = engine.generate(tid, custom_prompt=custom_text)
            else:
                from src.analytics.llm_prompts import PromptResult
                prompt = PromptResult(
                    id="custom",
                    template="custom",
                    prompt=custom_text,
                )

    # ── 渲染 Prompt 结果 ──
    if prompt:
        st.markdown("---")
        st.markdown("### 📝 生成的 Prompt")
        st.info("💡 复制以下内容 → 粘贴到豆包/DeepSeek/其他 LLM → 把回复贴回下方文本框")

        # Prominent copy button area
        st.code(prompt.prompt, language="markdown", line_numbers=False)

        # Download
        st.download_button(
            "📥 下载 Prompt (.md)",
            prompt.prompt,
            file_name=f"llm_prompt_{prompt.id}.md",
            mime="text/markdown",
        )

        # ── 回复输入区 ──
        st.markdown("---")
        st.markdown("### 📥 贴回 LLM 回复")

        response_text = st.text_area(
            "将 LLM 的回复粘贴到这里",
            height=250,
            placeholder="从豆包/DeepSeek 复制回复内容，粘贴到这里...",
            key=f"response_{prompt.id}",
        )

        if response_text:
            st.success("✅ 回复已记录")

            with st.expander("📊 查看结构化回复"):
                st.markdown(response_text)

            # 保存
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.download_button(
                    "💾 保存问答 (.md)",
                    f"# Prompt\n\n{prompt.prompt}\n\n---\n\n# 回复\n\n{response_text}",
                    file_name=f"qa_{prompt.id}.md",
                    mime="text/markdown",
                )
            with col_s2:
                if st.button("📋 复制完整问答"):
                    st.session_state["clipboard"] = (
                        f"{prompt.prompt}\n\n---\n\n{response_text}"
                    )
                    st.toast("已复制到剪贴板")


# ── 辅助函数 ──

def _job_selector(
    jobs: pd.DataFrame, key_prefix: str = ""
) -> pd.Series | None:
    """选择一个岗位，返回其 Series。"""
    # 搜索 + 下拉
    search = st.text_input(
        "搜索岗位",
        placeholder="输入关键词...",
        key=f"{key_prefix}_search",
    )

    df = jobs.copy()
    if search:
        mask = df["title"].str.contains(search, na=False) | df["company_name"].str.contains(
            search, na=False
        )
        df = df[mask]

    if "salary_avg" in df.columns:
        df = df.sort_values("salary_avg", ascending=False)

    options = []
    for _, r in df.head(50).iterrows():
        city = r.get("city", "")
        title = r.get("title", "")
        company = r.get("company_name", "")
        sal = r.get("salary_text", "")
        label = f"[{city}] {title} @ {company} {sal}"
        options.append((label, r.name))

    if not options:
        st.info("没有匹配的岗位")
        return None

    selected_label = st.selectbox(
        "选择",
        [o[0] for o in options],
        key=f"{key_prefix}_select",
    )
    selected_idx = [o[1] for o in options if o[0] == selected_label][0]
    return jobs.loc[selected_idx]


def _build_jd_text(row: pd.Series) -> str:
    """构建增强 JD 文本。"""
    parts = []
    if pd.notna(row.get("title")):
        parts.append(f"职位：{row['title']}")
    if pd.notna(row.get("company_name")):
        parts.append(f"公司：{row['company_name']}")
    if pd.notna(row.get("city")):
        parts.append(f"城市：{row['city']}")
    if pd.notna(row.get("salary_text")):
        parts.append(f"薪资：{row['salary_text']}")
    if pd.notna(row.get("experience")):
        parts.append(f"经验要求：{row['experience']}")
    if pd.notna(row.get("education")):
        parts.append(f"学历要求：{row['education']}")
    if pd.notna(row.get("skills")):
        parts.append(f"技术要求：{row['skills']}")
    if pd.notna(row.get("industry")):
        parts.append(f"行业：{row['industry']}")

    desc = row.get("description", "")
    if pd.notna(desc) and desc:
        parts.append(f"\n岗位描述：\n{desc}")

    return "\n".join(parts)
