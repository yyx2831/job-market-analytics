"""技能共现网络分析 — 基于岗位技能组合构建共现图，做社区发现与可视化。

核心能力：
- 构建加权无向图（节点=技能，边权重=共现次数）
- Louvain 社区检测（python-louvain）
- 中心性指标（度中心性、PageRank）
- 路径发现（最短技能升级路径）
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple, Any

import networkx as nx
import pandas as pd
from community import community_louvain  # type: ignore


# ── 图构建 ──

def build_skill_graph(
    jobs: pd.DataFrame,
    min_cooccur: int = 3,
    min_skill_len: int = 2,
) -> nx.Graph:
    """从岗位数据构建技能共现图。

    Args:
        jobs: 含 skills 列的 DataFrame
        min_cooccur: 边权重阈值，低于此值的共现关系被过滤
        min_skill_len: 技能名称最小长度（过滤噪声）

    Returns:
        加权无向图，节点属性含 count（出现次数），边属性含 weight（共现次数）
    """
    skills_col = jobs["skills"].dropna()
    if skills_col.empty:
        return nx.Graph()

    # 统计单个技能总频次
    skill_count: Counter = Counter()
    # 统计两两共现
    co_pairs: Counter = Counter()

    for skills_text in skills_col:
        tokens = _tokenize_skills(str(skills_text), min_length=min_skill_len)
        for t in tokens:
            skill_count[t] += 1
        for i, t1 in enumerate(tokens):
            for t2 in tokens[i + 1:]:
                # 统一排序 key，去重
                key = tuple(sorted([t1, t2]))
                co_pairs[key] += 1

    # 构建图
    G = nx.Graph()

    # 添加节点（只加出现 ≥ min_cooccur 的技能）
    for skill, cnt in skill_count.items():
        if cnt >= min_cooccur:
            G.add_node(skill, count=cnt)

    # 添加边
    for (s1, s2), weight in co_pairs.items():
        if weight >= min_cooccur and s1 in G and s2 in G:
            G.add_edge(s1, s2, weight=weight)

    return G


def _tokenize_skills(text: str, min_length: int = 2) -> List[str]:
    """从技能文本中提取 token 列表。"""
    tokens = []
    for t in re.split(r'[,;，；、\s]+', text):
        t = t.strip()
        if t and len(t) >= min_length:
            tokens.append(t)
    return tokens


# ── 社区检测 ──

def detect_communities(G: nx.Graph) -> Dict[str, int]:
    """Louvain 社区检测，返回 {技能: 社区ID}。"""
    if G.number_of_edges() == 0:
        return {}
    partition = community_louvain.best_partition(G)
    return partition  # type: ignore


def community_summary(G: nx.Graph, partition: Dict[str, int]) -> List[Dict[str, Any]]:
    """汇总每个社区的统计信息。"""
    communities: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
        "skills": [],
        "total_count": 0,
        "avg_centrality": 0.0,
        "main_skill": "",
        "main_count": 0,
    })

    dc = nx.degree_centrality(G) if G.number_of_nodes() > 0 else {}

    for node, comm_id in partition.items():
        comm = communities[comm_id]
        comm["skills"].append(node)
        cnt = G.nodes[node].get("count", 0)
        comm["total_count"] += cnt
        if cnt > comm["main_count"]:
            comm["main_count"] = cnt
            comm["main_skill"] = node

    # 排序
    result = []
    for comm_id, info in sorted(communities.items()):
        info["community_id"] = comm_id
        info["size"] = len(info["skills"])
        info["skills"] = sorted(info["skills"], key=lambda s: G.nodes[s].get("count", 0), reverse=True)
        result.append(info)

    # 按总需求数排序
    result.sort(key=lambda x: -x["total_count"])
    return result


# ── 中心性分析 ──

def compute_centrality(G: nx.Graph) -> pd.DataFrame:
    """计算每个技能的中心性指标。"""
    if G.number_of_nodes() == 0:
        return pd.DataFrame(columns=["skill", "count", "degree", "degree_centrality", "pagerank"])

    dc = nx.degree_centrality(G)
    pr = nx.pagerank(G, weight="weight")

    rows = []
    for node in G.nodes():
        rows.append({
            "skill": node,
            "count": G.nodes[node].get("count", 0),
            "degree": G.degree(node),
            "degree_centrality": round(dc.get(node, 0), 4),
            "pagerank": round(pr.get(node, 0), 6),
        })

    df = pd.DataFrame(rows)
    return df.sort_values("pagerank", ascending=False)


# ── 路径发现 ──

def find_skill_path(G: nx.Graph, start: str, end: str) -> Optional[List[str]]:
    """寻找两个技能之间的最短学习路径。"""
    if start not in G or end not in G:
        return None
    try:
        return nx.shortest_path(G, source=start, target=end, weight="weight")
    except nx.NetworkXNoPath:
        return None


def find_bridge_skills(G: nx.Graph) -> List[Tuple[str, float]]:
    """寻找桥接技能（高介数中心性），即连接不同技能社群的关键技能。"""
    if G.number_of_nodes() < 3:
        return []
    bc = nx.betweenness_centrality(G, weight="weight")
    sorted_bc = sorted(bc.items(), key=lambda x: -x[1])
    return sorted_bc[:15]


# ── 子图提取 ──

def ego_network(G: nx.Graph, skill: str, radius: int = 1) -> nx.Graph:
    """提取某个技能的邻域子图（含该技能为中心向外 radius 跳的所有边）。"""
    if skill not in G:
        return nx.Graph()
    nodes = set([skill])
    for _ in range(radius):
        frontier: Set[str] = set()
        for n in nodes:
            frontier.update(G.neighbors(n))
        nodes.update(frontier)
    return G.subgraph(nodes).copy()
