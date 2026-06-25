"""
LLM 增强分析标签页 — 展示 AI 视角的岗位评估结果。
包含：综合推荐排名、多维度评分分布、薪资竞争力矩阵、城市对比、对比分析。
"""

from __future__ import annotations

import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from typing import Optional, List, Dict, Any


def get_analysis_data(conn: sqlite3.Connection) -> pd.DataFrame:
    """获取分析数据（连表查询）。"""
    query = """
        SELECT
            a.*,
            j.title, j.company_name, j.city, j.salary_avg,
            j.salary_min, j.salary_max, j.salary_months,
            j.experience, j.education, j.industry,
            j.company_size, j.skills, j.description,
            j.source_job_id, j.publish_time
        FROM llm_analysis_batch a
        JOIN jobs j ON a.job_id = j.id
        WHERE j.salary_avg > 0
    """
    return pd.read_sql_query(query, conn)


def get_jd_analysis_data(conn: sqlite3.Connection) -> pd.DataFrame:
    """获取 JD 深度分析数据。"""
    query = """
        SELECT d.*, j.title, j.city, j.company_name, j.salary_avg, j.skills,
               a.recommendation_score, a.tech_relevance, a.growth_potential
        FROM jd_deep_analysis d
        JOIN jobs j ON d.job_id = j.id
        LEFT JOIN llm_analysis_batch a ON d.job_id = a.job_id
    """
    return pd.read_sql_query(query, conn)


def render_llm_analysis(db_path: str) -> None:
    """渲染 LLM 分析标签页。"""
    st.title("🧠 LLM 增强分析")

    conn = sqlite3.connect(db_path)
    df = get_analysis_data(conn)
    df_jd = get_jd_analysis_data(conn)
    conn.close()

    if df.empty:
        st.warning("暂无分析数据")
        return

    # 全局筛选器
    st.sidebar.header("🔍 LLM 分析筛选")
    cities = sorted(df['city'].dropna().unique())
    selected_cities = st.sidebar.multiselect("城市", cities, default=cities[:6])
    min_score = st.sidebar.slider("最低推荐指数", 1, 10, 5)
    salary_filter = st.sidebar.multiselect(
        "薪资竞争力", ['high', 'medium', 'low'],
        default=['high', 'medium']
    )

    df_f = df[
        (df['city'].isin(selected_cities)) &
        (df['recommendation_score'] >= min_score) &
        (df['salary_competitiveness'].isin(salary_filter))
    ]

    # ═══ Tab 子页 ═══
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 综合排名", "📈 多维评分", "💰 薪资矩阵", "🔬 对比分析", "📄 JD 深度分析"
    ])

    # ── Tab 1: 综合排名 ──
    with tab1:
        st.subheader(f"🏆 TOP 推荐岗位（{len(df_f)} 条符合条件）")

        top_n = st.slider("显示数量", 10, 100, 30, key='top_n')
        top_df = df_f.nlargest(top_n, 'recommendation_score')

        for i, (_, row) in enumerate(top_df.iterrows(), 1):
            score = row['recommendation_score']
            stars = "⭐" * score

            col1, col2, col3 = st.columns([4, 2, 1])
            with col1:
                st.markdown(f"""
                **{i}. [{score}分] {row['title']}**  
                🏢 {row['company_name']} | 📍 {row['city']} | 💰 ¥{row['salary_avg']:,.0f}
                """)
            with col2:
                tech = row['tech_relevance']
                growth = row['growth_potential']
                st.markdown(f"🔧技术{tech}  📈成长{growth}  📝JD{row['role_clarity']}")
            with col3:
                comp = row['salary_competitiveness']
                emoji = {'high': '🟢', 'medium': '🟡', 'low': '🔴'}.get(comp, '⚪')
                st.markdown(f"{emoji} {comp}")

            with st.expander(f"详情: {row['one_line_comment'][:60]}..."):
                st.markdown(f"**💰 薪资评估**: {row['salary_competitiveness_reason']}")
                st.markdown(f"**🏢 公司类型**: {row['company_type']}")
                st.markdown(f"**📊 职级**: {row['position_level_name']}")
                st.markdown(f"**💬 评价**: {row['one_line_comment']}")

                if row.get('skills'):
                    st.markdown(f"**🔧 技能**: {row['skills']}")
                if row.get('description') and len(str(row['description'])) > 20:
                    st.markdown("**📄 JD摘要**:")
                    desc = str(row['description'])[:500]
                    st.text(desc + ("..." if len(str(row['description'])) > 500 else ""))

    # ── Tab 2: 多维评分分析 ──
    with tab2:
        st.subheader("📈 多维度评分分布")

        col1, col2 = st.columns(2)

        with col1:
            # 推荐指数分布
            fig = px.histogram(
                df_f, x='recommendation_score', nbins=10,
                color='salary_competitiveness',
                color_discrete_map={'high': '#2ecc71', 'medium': '#f39c12', 'low': '#e74c3c'},
                title='推荐指数分布（按薪资竞争力着色）',
                labels={'recommendation_score': '推荐指数'},
                barmode='stack',
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # 技术现代度 vs 成长潜力散点图
            fig = px.scatter(
                df_f, x='tech_relevance', y='growth_potential',
                color='recommendation_score',
                size='salary_avg',
                hover_data=['title', 'city', 'company_name'],
                color_continuous_scale='Viridis',
                title='技术度 × 成长潜力（气泡=薪资）',
                labels={'tech_relevance': '技术现代度', 'growth_potential': '成长潜力'},
            )
            st.plotly_chart(fig, use_container_width=True)

        # 雷达图: 各维度均值
        col3, col4 = st.columns(2)

        with col3:
            # 城市维度雷达
            city_metrics = df_f.groupby('city').agg(
                tech=('tech_relevance', 'mean'),
                growth=('growth_potential', 'mean'),
                clarity=('role_clarity', 'mean'),
                recommend=('recommendation_score', 'mean'),
            ).reset_index()

            fig = px.line_polar(
                city_metrics.melt(id_vars='city', var_name='维度', value_name='分数'),
                r='分数', theta='维度', color='city',
                line_close=True,
                title='各城市多维度对比（雷达图）',
                range_r=[0, 10],
            )
            st.plotly_chart(fig, use_container_width=True)

        with col4:
            # 公司类型维度对比
            company_metrics = df_f.groupby('company_type').agg(
                tech=('tech_relevance', 'mean'),
                growth=('growth_potential', 'mean'),
                clarity=('role_clarity', 'mean'),
                recommend=('recommendation_score', 'mean'),
            ).reset_index()

            fig = px.bar(
                company_metrics.melt(id_vars='company_type', var_name='维度', value_name='平均分'),
                x='company_type', y='平均分', color='维度',
                barmode='group',
                title='各公司类型多维度对比',
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Tab 3: 薪资竞争力矩阵 ──
    with tab3:
        st.subheader("💰 薪资竞争力矩阵分析")

        col1, col2 = st.columns(2)

        with col1:
            # 薪资水平 vs 竞争力（箱线图）
            # 分城市
            city_order = df_f.groupby('city')['salary_avg'].median().sort_values(ascending=False).index.tolist()

            fig = px.box(
                df_f, x='city', y='salary_avg',
                color='salary_competitiveness',
                color_discrete_map={'high': '#2ecc71', 'medium': '#f39c12', 'low': '#e74c3c'},
                category_orders={'city': city_order},
                title='各城市薪资分布 × 竞争力评级',
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # salary_ratio 分布（实际薪资 vs 基准）
            fig = px.histogram(
                df_f, x='salary_ratio', nbins=50,
                color='salary_competitiveness',
                color_discrete_map={'high': '#2ecc71', 'medium': '#f39c12', 'low': '#e74c3c'},
                title='薪资比率分布（实际/基准）',
                labels={'salary_ratio': '薪资比率'},
                barmode='overlay',
            )
            fig.add_vline(x=1.0, line_dash='dash', line_color='gray', annotation_text='基准线')
            st.plotly_chart(fig, use_container_width=True)

        # 各城市高薪竞争力占比
        city_high = (
            df_f.groupby('city')
            .agg(
                total=('salary_competitiveness', 'count'),
                high_count=('salary_competitiveness', lambda x: (x == 'high').sum()),
            )
            .reset_index()
        )
        city_high['high_pct'] = (city_high['high_count'] / city_high['total'] * 100).round(1)
        city_high = city_high.sort_values('high_pct', ascending=False)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=city_high['city'],
            y=city_high['high_pct'],
            marker_color='#2ecc71',
            text=city_high['high_pct'].apply(lambda x: f'{x}%'),
            textposition='outside',
            name='高薪竞争力占比',
        ))
        fig.add_trace(go.Scatter(
            x=city_high['city'],
            y=city_high['total'],
            yaxis='y2',
            mode='lines+markers',
            marker_color='#3498db',
            name='岗位总数',
        ))
        # 隐藏 y2
        fig.update_layout(
            title='各城市高薪竞争力占比 + 岗位数',
            yaxis=dict(title='高薪占比 (%)', range=[0, 100]),
            xaxis_tickangle=-45,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Tab 4: 对比分析 (LLM vs 数据指标) ──
    with tab4:
        st.subheader("🔬 LLM 视角 vs 数据指标视角")

        st.markdown("""
        **对比维度说明**：
        - **LLM 视角**：基于规则引擎编码的专家判断（技术栈、公司、行业赛道、增长趋势）
        - **数据指标视角**：基于统计特征（薪资分位数、岗位数量、技能频次、发布活跃度）
        """)

        # 对比1: LLM评分 vs 实际薪资
        col1, col2 = st.columns(2)

        with col1:
            fig = px.scatter(
                df_f, x='recommendation_score', y='salary_avg',
                color='city', size='growth_potential',
                hover_data=['title', 'company_name'],
                trendline='ols',
                trendline_color_override='red',
                title='LLM推荐指数 vs 实际薪资（趋势线=线性回归）',
                labels={'recommendation_score': 'LLM推荐指数', 'salary_avg': '实际月薪'},
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # 对比2: 技术评分 vs 薪资
            fig = px.box(
                df_f, x='tech_relevance', y='salary_avg',
                color='salary_competitiveness',
                color_discrete_map={'high': '#2ecc71', 'medium': '#f39c12', 'low': '#e74c3c'},
                title='技术现代度 vs 薪资分布',
                labels={'tech_relevance': '技术现代度评分', 'salary_avg': '实际月薪'},
            )
            st.plotly_chart(fig, use_container_width=True)

        # 对比3: 城市级 LLM vs 数据指标偏差
        st.markdown("### 📊 城市级偏差分析：LLM评分 vs 薪资中位数排名")

        city_stats = df_f.groupby('city').agg(
            avg_recommend=('recommendation_score', 'mean'),
            median_salary=('salary_avg', 'median'),
            avg_tech=('tech_relevance', 'mean'),
            avg_growth=('growth_potential', 'mean'),
            job_count=('job_id', 'count'),
        ).reset_index()

        city_stats['salary_rank'] = city_stats['median_salary'].rank(ascending=False)
        city_stats['recommend_rank'] = city_stats['avg_recommend'].rank(ascending=False)
        city_stats['rank_diff'] = (city_stats['salary_rank'] - city_stats['recommend_rank']).abs()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=city_stats['salary_rank'],
            y=city_stats['recommend_rank'],
            mode='markers+text',
            text=city_stats['city'],
            textposition='top center',
            marker=dict(
                size=city_stats['job_count'] / 2,
                color=city_stats['rank_diff'],
                colorscale='RdYlGn_r',
                showscale=True,
                colorbar=dict(title='排名偏差'),
            ),
            hovertemplate='<b>%{text}</b><br>薪资排名: %{x}<br>LLM排名: %{y}<br>偏差: %{marker.color:.1f}<extra></extra>',
        ))
        fig.add_shape(type='line', x0=0, y0=0, x1=12, y1=12, line=dict(dash='dash', color='gray'))
        fig.update_layout(
            title='LLM推荐排名 vs 薪资排名（越靠近对角线=越一致）',
            xaxis=dict(title='薪资中位数排名（1=最高）', autorange='reversed'),
            yaxis=dict(title='LLM推荐排名（1=最高）', autorange='reversed'),
        )
        st.plotly_chart(fig, use_container_width=True)

        # 对比4: 技能视角差异
        st.markdown("### 🔧 技能视角差异：LLM看重的技能 vs 市场高频技能")

        from collections import Counter

        # 高评分岗位的技能 vs 全量技能
        high_scored = df_f[df_f['recommendation_score'] >= 8]
        all_skills = Counter()
        high_skills = Counter()

        for skills_str in df_f['skills'].dropna():
            for s in str(skills_str).split(','):
                skill = s.strip()
                if skill and len(skill) > 1:
                    all_skills[skill] += 1

        for skills_str in high_scored['skills'].dropna():
            for s in str(skills_str).split(','):
                skill = s.strip()
                if skill and len(skill) > 1:
                    high_skills[skill] += 1

        all_total = sum(all_skills.values())
        high_total = sum(high_skills.values())

        # 找出差异最大的技能
        skill_diff = []
        for skill in set(list(all_skills.keys()) + list(high_skills.keys())):
            all_pct = all_skills.get(skill, 0) / all_total * 100
            high_pct = high_skills.get(skill, 0) / high_total * 100 if high_total > 0 else 0
            skill_diff.append({
                'skill': skill,
                '全量频率(%)': round(all_pct, 1),
                '高分频率(%)': round(high_pct, 1),
                '差异': round(high_pct - all_pct, 1),
            })

        diff_df = pd.DataFrame(skill_diff).nlargest(30, '差异')

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**LLM偏好技能（在高分岗位中频率更高）**")
            top_diff = diff_df.nlargest(10, '差异')
            fig = px.bar(
                top_diff, x='差异', y='skill',
                orientation='h',
                color='差异',
                color_continuous_scale='Blues',
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("**全量最高频技能**")
            top_freq = sorted(all_skills.items(), key=lambda x: -x[1])[:10]
            freq_df = pd.DataFrame(top_freq, columns=['skill', 'count'])
            freq_df['pct'] = (freq_df['count'] / all_total * 100).round(1)
            fig = px.bar(
                freq_df, x='pct', y='skill',
                orientation='h',
                color='pct',
                color_continuous_scale='Greens',
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Tab 5: JD 深度分析 ──
    with tab5:
        st.subheader("📄 JD 描述深度 NLP 分析")

        if df_jd.empty:
            st.info("暂无 JD 深度分析数据，需要运行 jd_analyzer 扫描")
        else:
            # 整体统计卡片
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("已分析岗位", f"{len(df_jd):,}")
            with c2:
                st.metric("平均技术密度", str(round(df_jd['tech_density'].mean(), 1)))
            with c3:
                st.metric("平均结构分", f"{df_jd['jd_structure_score'].mean():.1f}/10")
            with c4:
                st.metric("平均关键词", f"{df_jd['tech_keywords_count'].mean():.0f}/JD")

            # 子Tab: 职能分布 / 结构质量 / 候选人画像
            subtab1, subtab2, subtab3 = st.tabs([
                "🎯 职能分布", "✅ JD 质量", "👤 候选人要求"
            ])

            with subtab1:
                col1, col2 = st.columns([1, 1])
                with col1:
                    # 职能分布饼图
                    func_counts = df_jd['function_category'].value_counts()
                    fig = px.pie(
                        names=func_counts.index, values=func_counts.values,
                        title="岗位职能分布",
                        color_discrete_sequence=px.colors.qualitative.Set3,
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    # 职能 × 技术密度
                    func_density = df_jd.groupby('function_category').agg(
                        count=('tech_density', 'count'),
                        avg_density=('tech_density', 'mean'),
                        avg_score=('recommendation_score', 'mean'),
                    ).round(1).reset_index()
                    func_density = func_density.sort_values('count', ascending=True)

                    fig = px.bar(
                        func_density, x='avg_density', y='function_category',
                        color='avg_score', orientation='h',
                        title="各职能技术密度 × 推荐分",
                        text=func_density['avg_density'].astype(str),
                        color_continuous_scale='RdYlGn',
                        range_color=[4, 8],
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with subtab2:
                col1, col2 = st.columns(2)
                with col1:
                    # JD 完整性
                    struct_data = {
                        '有职责描述': df_jd['has_responsibilities'].sum(),
                        '有技能要求': df_jd['has_requirements'].sum(),
                        '有福利待遇': df_jd['has_benefits'].sum(),
                        '有加分项': df_jd['has_preferred'].sum(),
                    }
                    total = len(df_jd)
                    struct_pct = {k: v/total*100 for k, v in struct_data.items()}
                    fig = px.bar(
                        x=list(struct_pct.keys()), y=list(struct_pct.values()),
                        title="JD 各章节覆盖率",
                        labels={'x': '章节', 'y': '%'},
                        text=[f'{v:.0f}%' for v in struct_pct.values()],
                        color=list(struct_pct.values()),
                        color_continuous_scale='Blues',
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    # 结构分分布
                    struct_dist = df_jd['jd_structure_score'].value_counts().sort_index()
                    fig = px.bar(
                        x=struct_dist.index, y=struct_dist.values,
                        title="JD 结构完整性评分分布",
                        labels={'x': '得分 (1-10)', 'y': '岗位数'},
                        color=struct_dist.index,
                        color_continuous_scale='RdYlGn',
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # 高分JD vs 低分JD 样本
                st.markdown("---")
                st.markdown("**📝 JD 质量对比**")
                col_good, col_bad = st.columns(2)
                with col_good:
                    good_jd = df_jd.nlargest(3, 'jd_structure_score')
                    for _, row in good_jd.iterrows():
                        st.caption(f"⭐ {row['jd_structure_score']}分 | {row['city']} | {row['title'][:25]}")
                with col_bad:
                    bad_jd = df_jd.nsmallest(3, 'jd_structure_score')
                    for _, row in bad_jd.iterrows():
                        st.caption(f"⭐ {row['jd_structure_score']}分 | {row['city']} | {row['title'][:25]}")

            with subtab3:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("学历覆盖", "")
                    edu_dist = df_jd['expected_education'].value_counts()
                    for edu, cnt in edu_dist.items():
                        st.metric(edu, f"{cnt} ({cnt/total*100:.0f}%)")

                with col2:
                    st.metric("经验要求", "")
                    exp_dist = df_jd['expected_experience'].value_counts().head(6)
                    for exp, cnt in exp_dist.items():
                        st.metric(exp, f"{cnt} ({cnt/total*100:.0f}%)")

                with col3:
                    st.metric("特殊要求", "")
                    eng_count = df_jd['english_required'].value_counts().get('是', 0)
                    mgmt_count = df_jd['management_required'].value_counts().get('是', 0)
                    oss_count = df_jd['oss_participation'].value_counts().get('加分', 0)
                    st.metric("要求英语", f"{eng_count} ({eng_count/total*100:.0f}%)")
                    st.metric("管理经验", f"{mgmt_count} ({mgmt_count/total*100:.0f}%)")
                    st.metric("开源加分", f"{oss_count} ({oss_count/total*100:.0f}%)")

    # 页脚统计
    st.sidebar.markdown("---")
    st.sidebar.metric("分析岗位数", f"{len(df_f):,}")
    st.sidebar.metric("平均推荐指数", f"{df_f['recommendation_score'].mean():.1f}/10")
    st.sidebar.metric(
        "高薪竞争力占比",
        f"{(df_f['salary_competitiveness'] == 'high').mean() * 100:.0f}%"
    )
