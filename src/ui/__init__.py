"""UI 组件模块 — Streamlit 仪表盘各标签页渲染函数。"""

from src.ui.overview import load_data, apply_filters, render_sidebar, render_overview
from src.ui.insights import render_insights
from src.ui.trends import render_trends
from src.ui.salary import render_salary_analysis
from src.ui.cities import render_city_compare
from src.ui.table import render_job_table
from src.ui.skill_guide import render_skill_guide
from src.ui.skill_network import render_skill_network
from src.ui.salary_trend import render_salary_trend

from src.ui.employers import render_employers
from src.ui.recommender import render_recommender
from src.ui.competitiveness import render_competitiveness
from src.ui.llm_prompts import render_llm_prompts
from src.ui.llm_analysis import render_llm_analysis
from src.ui.salary_predictor import render_salary_predictor
from src.ui.chengdu_vs_national import render_chengdu_vs_national
from src.ui.job_recommender import render_chengdu_recommender
from src.ui.chengdu_special import render_chengdu_special

__all__ = [
    "load_data",
    "apply_filters",
    "render_sidebar",
    "render_overview",
    "render_insights",
    "render_trends",
    "render_salary_analysis",
    "render_city_compare",
    "render_job_table",
    "render_skill_guide",
    "render_skill_network",
    "render_salary_trend",
    "render_employers",
    "render_recommender",
    "render_competitiveness",
    "render_llm_prompts",
    "render_llm_analysis",
    "render_salary_predictor",
    "render_chengdu_vs_national",
    "render_chengdu_recommender",
    "render_chengdu_special",
]
