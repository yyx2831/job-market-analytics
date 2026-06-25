"""技能共现网络标签页 — 交互式技能关系图、社区检测、路径发现。"""

from typing import Dict, List, Optional, Any

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.skill_network import (
    build_skill_graph,
    detect_communities,
    community_summary,
    compute_centrality,
    find_skill_path,
    find_bridge_skills,
    ego_network,
)


def render_skill_network(jobs: pd.DataFrame) -> None:
    """渲染技能网络标签页。"""
    st.subheader("🔗 技能共现网络")

    # ── 参数 ──
    col1, col2, col3 = st.columns(3)
    with col1:
        min_co = st.slider("最小共现次数", 2, 20, 5,
                           help="边权重阈值：两个技能至少同时出现 N 次才显示连线")
    with col2:
        max_nodes = st.slider("最大节点数", 20, 150, 80,
                              help="限制节点数以保证可读性")
    with col3:
        viz_mode = st.selectbox("可视化模式", ["force", "circular"],
                                help="force: 力导向布局 | circular: 环形布局")

    # ── 构建图 ──
    G = build_skill_graph(jobs, min_cooccur=min_co)

    if G.number_of_nodes() == 0:
        st.warning("当前筛选条件下无足够数据构建技能网络。请尝试降低「最小共现次数」。")
        return

    # 限制节点数（取 count 最高的 N 个）
    if G.number_of_nodes() > max_nodes:
        top_nodes = sorted(G.nodes(), key=lambda n: G.nodes[n].get("count", 0), reverse=True)[:max_nodes]
        G = G.subgraph(top_nodes).copy()

    st.caption(
        f"共 {G.number_of_nodes()} 个技能节点，{G.number_of_edges()} 条共现边 "
        f"（最小共现={min_co}）"
    )

    # ── 社区检测 ──
    partition = detect_communities(G)
    communities = community_summary(G, partition) if partition else []

    # ── 双列布局：网络图 + 指标 ──
    col_net, col_info = st.columns([2, 1])

    with col_net:
        fig = _render_network_plotly(G, partition, viz_mode)
        st.plotly_chart(fig, use_container_width=True)

    with col_info:
        st.markdown("**📊 网络指标**")
        if G.number_of_nodes() > 0:
            density = nx.density(G)
            components = nx.number_connected_components(G)
            avg_clustering = nx.average_clustering(G, weight="weight")

            st.metric("图密度", f"{density:.4f}")
            st.metric("连通分量", components)
            st.metric("平均聚类系数", f"{avg_clustering:.3f}")

            if communities:
                st.markdown(f"**🏘️ 技能社群 ({len(communities)} 个)**")
                for info in communities[:6]:
                    with st.expander(
                        f"{info['main_skill']} 社群 ({info['size']}技能)",
                        expanded=len(communities) <= 3,
                    ):
                        skills_str = "、".join(info["skills"][:8])
                        if len(info["skills"]) > 8:
                            skills_str += f"… 等{len(info['skills'])}项"
                        st.caption(skills_str)
                        st.caption(f"总需求次数: {info['total_count']}")

    # ── 中心性排行 ──
    st.markdown("---")
    st.subheader("🏆 技能中心性排行")

    centrality = compute_centrality(G)

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("**核心枢纽技能 (PageRank)**")
        st.caption("高 PageRank = 被高频技能关联，在技术栈中处于枢纽位置")
        top_pr = centrality.head(15)
        fig_pr = go.Figure(data=[
            go.Bar(
                x=top_pr["pagerank"],
                y=top_pr["skill"],
                orientation="h",
                marker=dict(color=top_pr["pagerank"], colorscale="teal"),
            )
        ])
        fig_pr.update_layout(
            height=400,
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="PageRank",
        )
        st.plotly_chart(fig_pr, use_container_width=True)

    with col_c2:
        st.markdown("**桥接技能 (介数中心性)**")
        st.caption("高介数 = 连接不同技术社群的关键节点，「跨界的价值」")
        bridges = find_bridge_skills(G)
        if bridges:
            bridge_df = pd.DataFrame(bridges, columns=["skill", "betweenness"])
            bridge_df = bridge_df.head(15)
            fig_bc = go.Figure(data=[
                go.Bar(
                    x=bridge_df["betweenness"],
                    y=bridge_df["skill"],
                    orientation="h",
                    marker=dict(color=bridge_df["betweenness"], colorscale="mint"),
                )
            ])
            fig_bc.update_layout(
                height=400,
                yaxis={"categoryorder": "total ascending"},
                xaxis_title="介数中心性",
            )
            st.plotly_chart(fig_bc, use_container_width=True)
        else:
            st.info("图太小，介数中心性无意义")

    # ── 路径发现 ──
    st.markdown("---")
    st.subheader("🛤️ 技能升级路径")

    all_skills = sorted(G.nodes())
    if len(all_skills) >= 2:
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            start = st.selectbox("起点技能", all_skills, index=0, key="path_start")
        with col_s2:
            # 默认选一个不同的
            default_end = all_skills[1] if all_skills[0] == start else all_skills[0]
            try:
                end_idx = all_skills.index(default_end)
            except ValueError:
                end_idx = 0
            end = st.selectbox("目标技能", all_skills, index=end_idx, key="path_end")

        if start and end and start != end:
            path = find_skill_path(G, start, end)
            if path:
                st.success(f"最短路径 ({len(path)-1} 步): {'  →  '.join(path)}")
                st.caption("路径上的每个技能都是一个学习节点，中间的技能就是你需要补的课。")

                # 高亮路径子图
                path_sub = G.subgraph(path).copy()
                fig_path = _render_network_plotly(
                    path_sub,
                    {},  # no partition coloring for paths
                    "force",
                    highlight_nodes=set(path),
                )
                st.plotly_chart(fig_path, use_container_width=True)
            else:
                st.warning(f"「{start}」和「{end}」之间无连通路径（属于不同技能社群）")

    # ── 热门技能领域子图 ──
    if communities:
        st.markdown("---")
        st.subheader("🔍 技能社群速览")
        st.caption("选择社群查看内部技能关系")

        comm_options = {
            f"{info['main_skill']} 社群 ({info['size']}技能)": info
            for info in communities
        }
        selected_comm_label = st.selectbox("选择社群", list(comm_options.keys()))
        if selected_comm_label:
            info = comm_options[selected_comm_label]
            comm_nodes = set(info["skills"])
            comm_sub = G.subgraph(comm_nodes).copy()
            comm_partition = {n: 0 for n in comm_nodes}  # 单一颜色
            fig_comm = _render_network_plotly(comm_sub, comm_partition, "force")
            fig_comm.update_layout(
                title=f"{info['main_skill']} 社群 · {info['size']} 个技能 · {comm_sub.number_of_edges()} 条边"
            )
            st.plotly_chart(fig_comm, use_container_width=True)


# ── Plotly 网络图渲染 ──

def _render_network_plotly(
    G: nx.Graph,
    partition: Dict[str, int],
    layout_mode: str,
    highlight_nodes: Optional[set] = None,
) -> go.Figure:
    """用 Plotly 渲染网络图。

    支持力导向（spring_layout）和环形（circular_layout）两种布局。
    """
    if G.number_of_nodes() == 0:
        return go.Figure()

    # 布局
    if layout_mode == "circular":
        pos = nx.circular_layout(G)
    else:
        pos = nx.spring_layout(G, k=2.5, iterations=50, seed=42, weight="weight")

    # 节点大小（按 count 缩放）
    max_count = max((G.nodes[n].get("count", 1) for n in G.nodes()), default=1)
    node_sizes = [
        8 + (G.nodes[n].get("count", 1) / max_count) * 30
        for n in G.nodes()
    ]

    # 节点颜色（按社区）
    color_palette = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]
    node_colors = []
    for n in G.nodes():
        comm = partition.get(n, -1)
        if highlight_nodes and n in highlight_nodes:
            color = "#FFD700"
        else:
            color = color_palette[comm % len(color_palette)] if comm >= 0 else "#999999"
        node_colors.append(color)

    # 边（宽度按权重缩放）
    max_weight = max((d.get("weight", 1) for _, _, d in G.edges(data=True)), default=1)
    edge_x: list = []
    edge_y: list = []
    edge_widths: list = []
    edge_colors: list[str] = []

    for u, v, d in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        w = d.get("weight", 1)
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        edge_widths.append(max(0.5, (w / max_weight) * 5))
        # 同社区边用半透明色
        if partition.get(u) == partition.get(v) >= 0:
            edge_colors.append("rgba(150,150,150,0.3)")
        else:
            edge_colors.append("rgba(200,200,200,0.15)")

    # 渲染边
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=1, color="rgba(180,180,180,0.25)"),
        hoverinfo="none",
        showlegend=False,
    ))

    # 渲染节点
    node_hover_texts = []
    for n in G.nodes():
        cnt = G.nodes[n].get("count", 0)
        deg = G.degree(n)
        comm = partition.get(n, "")
        txt = f"<b>{n}</b><br>需求: {cnt}次<br>关联技能: {deg}个"
        if comm != "":
            txt += f"<br>社群: {comm}"
        node_hover_texts.append(txt)

    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in G.nodes()],
        y=[pos[n][1] for n in G.nodes()],
        mode="markers+text",
        marker=dict(
            size=node_sizes,
            color=node_colors,
            line=dict(width=1, color="white"),
            opacity=0.85,
        ),
        text=[n for n in G.nodes()],
        textposition="top center",
        textfont=dict(size=10),
        hovertext=node_hover_texts,
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        showlegend=False,
        hovermode="closest",
        margin=dict(l=0, r=0, t=20, b=0),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig
