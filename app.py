"""Job Market Analytics — Streamlit 仪表盘。

17 个标签页：概览 / 洞察 / 趋势 / 薪资分析 / 城市对比 / 明细 / 学习路线 / 技能网络 / 薪资追踪 / 雇主画像 / 智能推荐 / 竞争力 / LLM 增强 / LLM 分析 / 薪资预测 / 成都vs全国 / 岗位推荐。

用法:
  streamlit run app.py
"""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from src.database import connect
from src.nlp import classify_dataframe
from src.ui import (
    load_data, apply_filters, render_sidebar,
    render_overview, render_insights, render_trends,
    render_salary_analysis, render_city_compare,
    render_job_table, render_skill_guide,
    render_skill_network, render_salary_trend,
    render_employers, render_recommender,
    render_competitiveness, render_llm_prompts,
    render_llm_analysis, render_salary_predictor,
    render_chengdu_vs_national,
    render_chengdu_recommender,
    render_chengdu_special,
)

st.set_page_config(
    page_title="Job Market Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_PATH = ROOT / "data" / "processed" / "jobs.db"


def main():
    st.title("📊 城市岗位大数据分析平台")
    st.caption("数据来源：51job + 阿里/小米/美团/网易/字节/腾讯 · 10,044+ 岗位 · SQLite 存储 · NLP 技能提取")

    conn = connect(DB_PATH)
    jobs_all = load_data(conn)
    conn.close()

    if jobs_all.empty:
        st.error("数据库为空，请先运行采集脚本。")
        return

    # 自动分类（新增 category 列）
    jobs_all = classify_dataframe(jobs_all)

    filters = render_sidebar(jobs_all)

    # 城市范围过滤
    filtered = jobs_all.copy()
    if filters["selected_cities"]:
        filtered = filtered[filtered["city"].isin(filters["selected_cities"])]

    # 类别过滤
    if filters.get("selected_categories"):
        filtered = filtered[filtered["category"].isin(filters["selected_categories"])]

    # 通用过滤
    filtered = apply_filters(
        filtered,
        keyword=filters["keyword"],
        real_only=filters["real_only"],
        skills_filter=filters["skills_filter"],
    )

    # ── Tab 标签页（注入 CSS + JS 支持横向滚动 & 左右箭头） ──
    _inject_tab_scroll_css()

    tabs = st.tabs([
        "📈 概览", "🧠 观点", "📊 趋势",
        "💰 薪资分析", "🌍 城市对比", "📋 明细",
        "🐼 成都深度",
        "📚 学习路线", "🔗 技能网络", "📈 薪资追踪",
        "🏢 雇主画像", "🎯 智能推荐", "🏅 竞争力", "🤖 LLM 增强",
        "🧠 LLM 分析", "🔮 薪资预测",
        "🏙 成都vs全国",
        "🎯 岗位推荐",
    ])

    _inject_tab_scroll_js()

    # ── PDF 导出（侧边栏按钮） ──
    st.sidebar.markdown("---")
    city_str = f"{filters['selected_cities'][0]}" if len(filters["selected_cities"]) == 1 else (
        f"{len(filters['selected_cities'])} 城" if filters["selected_cities"] else "全部"
    )
    if st.sidebar.button("📄 导出 PDF 报告", use_container_width=True, help="生成当前筛选条件下的分析报告"):
        from src.ui.pdf_report import generate_report
        with st.spinner("正在生成报告..."):
            report_buf = generate_report(filtered, city_str)
        st.sidebar.download_button(
            "⬇️ 下载报告", data=report_buf, file_name=f"job_report_{city_str}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf", use_container_width=True,
        )
    with tabs[0]:
        render_overview(filtered, filters["selected_cities"])
    with tabs[1]:
        render_insights(filtered)
    with tabs[2]:
        render_trends(filtered)
    with tabs[3]:
        render_salary_analysis(filtered)
    with tabs[4]:
        render_city_compare(jobs_all)
    with tabs[5]:
        render_job_table(filtered)
    with tabs[6]:
        render_chengdu_special(DB_PATH)
    with tabs[7]:
        render_skill_guide()
    with tabs[8]:
        render_skill_network(filtered)
    with tabs[9]:
        render_salary_trend(DB_PATH)
    with tabs[10]:
        render_employers(jobs_all)
    with tabs[11]:
        render_recommender(jobs_all)
    with tabs[12]:
        render_competitiveness(jobs_all)
    with tabs[13]:
        render_llm_prompts(jobs_all)
    with tabs[14]:
        render_llm_analysis(DB_PATH)
    with tabs[15]:
        render_salary_predictor(DB_PATH)
    with tabs[16]:
        render_chengdu_vs_national(DB_PATH)
    with tabs[17]:
        render_chengdu_recommender(jobs_all)


def _inject_tab_scroll_css():
    """注入 CSS：让 tab-list 支持横向滚动 + 细滚动条 + 箭头按钮样式。"""
    st.markdown("""
<style>
/* ── Tab 横向滚动容器 ── */
[data-baseweb="tab-list"] {
    overflow-x: auto !important;
    overflow-y: hidden !important;
    flex-wrap: nowrap !important;
    scroll-behavior: smooth;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
    scrollbar-color: #ccc transparent;
    padding-bottom: 4px;
    gap: 6px !important;
}
[data-baseweb="tab-list"]::-webkit-scrollbar {
    height: 5px;
}
[data-baseweb="tab-list"]::-webkit-scrollbar-track {
    background: transparent;
}
[data-baseweb="tab-list"]::-webkit-scrollbar-thumb {
    background: #c0c0c0;
    border-radius: 3px;
}
[data-baseweb="tab-list"]::-webkit-scrollbar-thumb:hover {
    background: #999;
}
/* ── 箭头按钮样式 ── */
.tab-scroll-btn {
    cursor: pointer;
    border: 1px solid #e0e0e0;
    background: #fafafa;
    border-radius: 6px;
    width: 30px;
    height: 34px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    color: #666;
    transition: all .15s;
    flex-shrink: 0;
    user-select: none;
    line-height: 1;
}
.tab-scroll-btn:hover {
    background: #e8e8e8;
    color: #333;
    border-color: #bbb;
}
.tab-scroll-btn:active {
    background: #d0d0d0;
}
.tab-scroll-btn.faded {
    opacity: 0.25;
    pointer-events: none;
}
</style>
    """, unsafe_allow_html=True)


def _inject_tab_scroll_js():
    """注入 JS：在 tab-list 左右两侧添加箭头按钮，滚轮横向滚动。"""
    from streamlit.components.v1 import html
    html("""
<script>
(function() {
    const SEL = '[data-baseweb="tab-list"]';
    const SCROLL = 280;  // 每次滚动像素

    function setup() {
        const tabList = window.parent.document.querySelector(SEL);
        if (!tabList) return;
        if (tabList.dataset.scrollReady) return;
        tabList.dataset.scrollReady = '1';

        // 创建外层 flex 容器
        const wrapper = window.parent.document.createElement('div');
        wrapper.style.cssText = 'display:flex;align-items:stretch;gap:4px;width:100%;';
        tabList.parentNode.insertBefore(wrapper, tabList);

        // 左箭头
        const leftBtn = window.parent.document.createElement('div');
        leftBtn.className = 'tab-scroll-btn';
        leftBtn.textContent = '\u25C0';
        leftBtn.title = '向左滚动';
        leftBtn.addEventListener('click', function() {
            tabList.scrollBy({ left: -SCROLL, behavior: 'smooth' });
        });

        // 把 tabList 移入 wrapper
        wrapper.appendChild(leftBtn);
        wrapper.appendChild(tabList);

        // 右箭头
        const rightBtn = window.parent.document.createElement('div');
        rightBtn.className = 'tab-scroll-btn';
        rightBtn.textContent = '\u25B6';
        rightBtn.title = '向右滚动';
        rightBtn.addEventListener('click', function() {
            tabList.scrollBy({ left: SCROLL, behavior: 'smooth' });
        });
        wrapper.appendChild(rightBtn);

        // 滚轮 → 横向滚动
        tabList.addEventListener('wheel', function(e) {
            if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
            e.preventDefault();
            tabList.scrollLeft += e.deltaY;
        }, { passive: false });

        // 更新箭头显隐
        function updateArrows() {
            var atStart = tabList.scrollLeft <= 1;
            var atEnd = tabList.scrollLeft + tabList.clientWidth >= tabList.scrollWidth - 2;
            leftBtn.classList.toggle('faded', atStart);
            rightBtn.classList.toggle('faded', atEnd);
        }
        tabList.addEventListener('scroll', updateArrows);
        window.addEventListener('resize', updateArrows);
        // 初始状态 + MutationObserver（tab 切换后重算）
        updateArrows();
        setTimeout(updateArrows, 200);
        setTimeout(updateArrows, 800);
    }

    // 轮询等待 tab-list 出现在 DOM（Streamlit 异步渲染）
    var attempts = 0;
    var timer = setInterval(function() {
        attempts++;
        var el = window.parent.document.querySelector(SEL);
        if (el && !el.dataset.scrollReady) {
            setup();
            clearInterval(timer);
        } else if (attempts > 60) {
            clearInterval(timer);
        }
    }, 300);
})();
</script>
    """, height=0)


if __name__ == "__main__":
    main()
