"""Plot generation for ASHR simulation outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

from .utils import ensure_dir


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_topology(graph: nx.Graph, output_dir: str | Path) -> Path:
    output_dir = ensure_dir(output_dir)
    path = output_dir / "topology.png"
    positions = {
        "R1": (0.0, 1.2),
        "R2": (1.1, 1.7),
        "R3": (2.2, 1.7),
        "R4": (0.9, 0.4),
        "R5": (2.0, 0.4),
        "R6": (3.1, 0.4),
        "ABR1": (3.4, 1.7),
        "ABR2": (4.7, 1.1),
        "R7": (4.7, 2.1),
        "R8": (5.9, 1.0),
        "R9": (6.0, 2.0),
        "R10": (7.2, 1.5),
    }
    colors = []
    for node in graph.nodes:
        area = graph.nodes[node]["area_id"]
        if area == 0:
            colors.append("#4c78a8")
        elif area == 1:
            colors.append("#59a14f")
        else:
            colors.append("#f28e2b")

    fig, ax = plt.subplots(figsize=(11, 5.8))
    active_edges = [(u, v) for u, v, data in graph.edges(data=True) if not data.get("failed", False)]
    failed_edges = [(u, v) for u, v, data in graph.edges(data=True) if data.get("failed", False)]
    nx.draw_networkx_nodes(graph, positions, node_color=colors, node_size=1150, edgecolors="#222222", linewidths=1.0, ax=ax)
    nx.draw_networkx_labels(graph, positions, font_size=9, font_weight="bold", ax=ax)
    nx.draw_networkx_edges(graph, positions, edgelist=active_edges, width=1.8, edge_color="#555555", ax=ax)
    if failed_edges:
        nx.draw_networkx_edges(graph, positions, edgelist=failed_edges, width=2.5, edge_color="#d62728", style="dashed", ax=ax)
    edge_labels = {
        (u, v): f"{data['latency_ms']:.0f}ms/{data['bandwidth_mbps']:.0f}M"
        for u, v, data in graph.edges(data=True)
    }
    nx.draw_networkx_edge_labels(graph, positions, edge_labels=edge_labels, font_size=7, ax=ax)
    ax.set_title("ASHR Hierarchical Topology")
    ax.axis("off")
    _save(fig, path)
    return path


def plot_bar(
    rows: list[dict[str, object]],
    x_key: str,
    y_key: str,
    title: str,
    ylabel: str,
    output_dir: str | Path,
    filename: str,
    color_key: str | None = None,
) -> Path:
    output_dir = ensure_dir(output_dir)
    path = output_dir / filename
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    if color_key and color_key in df:
        labels = [f"{row[x_key]}\n{row[color_key]}" for _, row in df.iterrows()]
    else:
        labels = df[x_key].astype(str).tolist()
    colors = [
        "#4c78a8",
        "#f58518",
        "#54a24b",
        "#e45756",
        "#72b7b2",
        "#b279a2",
        "#ff9da6",
        "#9d755d",
        "#bab0ac",
        "#2f4b7c",
    ][: len(df)]
    ax.bar(labels, df[y_key], color=colors)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    ax.grid(axis="y", alpha=0.25)
    _save(fig, path)
    return path


def plot_path_cost(rows: list[dict[str, object]], output_dir: str | Path) -> Path:
    return plot_bar(
        rows,
        x_key="label",
        y_key="cost",
        title="Path Cost Comparison",
        ylabel="Protocol-specific path cost",
        output_dir=output_dir,
        filename="path_cost_comparison.png",
    )
