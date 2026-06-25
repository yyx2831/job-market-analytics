"""薪资预测仪表盘标签页 — 交互式预测 + 模型报告 + 批量对比"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

from src.analytics.salary_predictor import SalaryPredictor


def render_salary_predictor(db_path: str | Path) -> None:
    """渲染薪资预测标签页"""
    st.subheader("🔮 薪资预测模型")

    model_path = Path(db_path).parent / "salary_model.pkl"

    if not model_path.exists():
        st.warning("模型未训练，请先生成模型文件。")
        if st.button("🚀 训练模型"):
            import sqlite3
            conn = sqlite3.connect(db_path)
            df = pd.read_sql("SELECT * FROM jobs WHERE salary_avg > 0 AND salary_unit = 'month'", conn)
            conn.close()
            pred = SalaryPredictor()
            metrics = pred.train(df)
            pred.save(str(model_path))
            st.success(f"训练完成！R²={metrics['rf_r2']:.4f}, MAE=¥{metrics['rf_mae']:.0f}")
            st.rerun()
        return

    pred = SalaryPredictor.load(str(model_path))

    col_left, col_right = st.columns([1, 1])

    # ──── 左侧: 交互式预测 ────
    with col_left:
        st.markdown("### 🎯 输入你的条件")

        col_a, col_b = st.columns(2)
        with col_a:
            city = st.selectbox("城市", list(SalaryPredictor.CITY_BASELINE.keys()), index=5)
            experience = st.selectbox("经验", list(SalaryPredictor.EXPERIENCE_MULTIPLIER.keys()), index=5)
        with col_b:
            education = st.selectbox("学历", list(SalaryPredictor.EDUCATION_MULTIPLIER.keys()), index=3)
            company_size = st.selectbox("公司规模", [
                "少于15人", "15-50人", "50-150人", "150-500人",
                "500-1000人", "1000-5000人", "5000-10000人", "10000人以上",
            ], index=3)

        industry = st.selectbox("行业", [
            "计算机软件", "互联网", "通信", "电子技术", "金融", "医疗", "汽车", "机械", "教育", "房地产", "其他",
        ])

        skills_input = st.text_input(
            "技能（逗号分隔）", "Python,SQL,Docker",
            help="输入你掌握的技能，用逗号分隔"
        )
        skills = [s.strip() for s in skills_input.split(",") if s.strip()]

        if st.button("💰 预测薪资", type="primary", use_container_width=True):
            result = pred.predict(
                city=city, experience=experience, education=education,
                skills=skills, company_size=company_size, industry=industry,
            )
            if result.get("error"):
                st.error(result["error"])
            else:
                st.metric("预测月薪", result["monthly"])
                st.metric("预估年薪(12薪)", result["annual"], delta="±15%")
                st.metric("预估年薪(15薪)", result["annual_15"], delta="假设15薪")

    # ──── 右侧: 模型报告 ────
    with col_right:
        st.markdown("### 📊 模型报告")
        metrics = pred.metrics

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("R²", f"{metrics.get('rf_r2', 0):.3f}", help="随机森林决定系数")
        col_m2.metric("MAE", f"¥{metrics.get('rf_mae', 0):.0f}", help="平均绝对误差（月薪）")
        col_m3.metric("样本", f"{metrics.get('samples', 0)}条")

        st.markdown("#### 📈 特征重要性")
        importance_df = pd.DataFrame(
            list(pred.rf_importance.items())[:10],
            columns=["特征", "重要性"],
        )
        fig = go.Figure(go.Bar(
            x=importance_df["重要性"],
            y=importance_df["特征"],
            orientation="h",
            marker_color="steelblue",
        ))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # Explanation
        st.caption(
            "解释：特征重要性表示该因素对薪资预测的贡献。"
            "技能数量 + 经验年限是最关键的两个预测因子。"
        )

    # ──── 批量对比 ────
    st.markdown("---")
    st.markdown("### 📋 城市 × 经验 薪资矩阵")

    st.caption("按城市和经验级别预测的薪资热力图（默认：本科，2项技能）")

    cities = list(SalaryPredictor.CITY_BASELINE.keys())[:8]
    exps = ["无需经验", "1-3年", "3年及以上", "5年及以上", "8年及以上"]

    matrix = []
    for city in cities:
        row = []
        for exp in exps:
            r = pred.predict(city=city, experience=exp, education="本科", skills=["Python", "SQL"])
            row.append(r.get("salary_k", 0))
        matrix.append(row)

    # Heatmap
    fig2 = go.Figure(data=go.Heatmap(
        z=matrix,
        x=exps,
        y=cities,
        text=[[f"¥{v:.1f}K" for v in row] for row in matrix],
        texttemplate="%{text}",
        colorscale="RdYlGn",
        zmin=0, zmax=40,
    ))
    fig2.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig2, use_container_width=True)

    # ──── 实际 vs 预测 ────
    st.markdown("---")
    st.markdown("### 📉 预测 vs 实际 (抽样验证)")

    import sqlite3
    conn = sqlite3.connect(db_path)
    df_val = pd.read_sql(
        "SELECT city, experience, education, skills, company_size, industry, salary_avg "
        "FROM jobs WHERE salary_avg > 0 AND salary_unit = 'month' "
        "ORDER BY RANDOM() LIMIT 50", conn
    )
    conn.close()

    pred_vals = []
    for _, row in df_val.iterrows():
        r = pred.predict(
            city=row["city"] or "成都",
            experience=row["experience"] or "3年及以上",
            education=row["education"] or "本科",
            skills=[s.strip() for s in str(row.get("skills", "")).split(",") if s.strip()],
            company_size=row.get("company_size", "150-500人") or "150-500人",
            industry=row.get("industry", "计算机软件") or "计算机软件",
        )
        pred_vals.append(r.get("prediction", 0))

    actual = df_val["salary_avg"].values / 1000
    predicted = [p / 1000 for p in pred_vals]

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=actual, y=predicted,
        mode="markers",
        marker=dict(size=8, opacity=0.6, color="steelblue"),
        name="预测 vs 实际",
        text=[f"{c}" for c in df_val["city"]],
    ))
    # Perfect prediction line
    max_val = max(max(actual), max(predicted)) + 5
    fig3.add_trace(go.Scatter(
        x=[0, max_val], y=[0, max_val],
        mode="lines", line=dict(dash="dash", color="red", width=1),
        name="完美预测",
    ))
    fig3.update_layout(
        xaxis_title="实际月薪 (K)",
        yaxis_title="预测月薪 (K)",
        height=400,
    )
    st.plotly_chart(fig3, use_container_width=True)
    st.caption("点越接近红线，预测越准确。上方=高估，下方=低估。")
