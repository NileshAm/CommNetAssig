"""Plot generation for ASHR simulation outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from matplotlib.lines import Line2D

from .utils import ensure_dir


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _study_topology_positions() -> dict[str, tuple[float, float]]:
    return {
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


def _path_edges(path: list[str]) -> set[tuple[str, str]]:
    return {tuple(sorted((u, v))) for u, v in zip(path, path[1:])}


def plot_topology(graph: nx.Graph, output_dir: str | Path) -> Path:
    output_dir = ensure_dir(output_dir)
    path = output_dir / "topology.png"
    positions = _study_topology_positions()
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


def plot_congestion_before_after_path(
    graph: nx.Graph,
    before_path: list[str],
    after_path: list[str],
    output_dir: str | Path,
) -> Path:
    output_dir = ensure_dir(output_dir)
    path = output_dir / "congestion_before_after_path.png"
    positions = _study_topology_positions()
    before_edges = _path_edges(before_path)
    after_edges = _path_edges(after_path)
    overlap_edges = before_edges & after_edges
    before_only_edges = before_edges - overlap_edges
    after_only_edges = after_edges - overlap_edges

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
    nx.draw_networkx_edges(graph, positions, width=1.2, edge_color="#c9c9c9", ax=ax)
    nx.draw_networkx_nodes(graph, positions, node_color=colors, node_size=1150, edgecolors="#222222", linewidths=1.0, ax=ax)
    nx.draw_networkx_labels(graph, positions, font_size=9, font_weight="bold", ax=ax)

    def draw_highlight(edge_keys: set[tuple[str, str]], color: str, width: float, style: str) -> None:
        edges = [(u, v) for u, v in edge_keys if graph.has_edge(u, v)]
        if edges:
            nx.draw_networkx_edges(graph, positions, edgelist=edges, width=width, edge_color=color, style=style, ax=ax)

    draw_highlight(overlap_edges, "#6f4e9b", 3.2, "solid")
    draw_highlight(before_only_edges, "#e45756", 3.5, "dashed")
    draw_highlight(after_only_edges, "#008b8b", 3.5, "solid")

    congested_edge = ("ABR1", "ABR2")
    if graph.has_edge(*congested_edge):
        nx.draw_networkx_edges(
            graph,
            positions,
            edgelist=[congested_edge],
            width=5.2,
            edge_color="#b22222",
            style="dotted",
            ax=ax,
        )
        x1, y1 = positions["ABR1"]
        x2, y2 = positions["ABR2"]
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 - 0.25, "congested link", ha="center", fontsize=8, color="#8b0000")

    ax.legend(
        handles=[
            Line2D([0], [0], color="#6f4e9b", lw=3, label="Unchanged ASHR path links"),
            Line2D([0], [0], color="#e45756", lw=3, linestyle="--", label="Before congestion only"),
            Line2D([0], [0], color="#008b8b", lw=3, label="After congestion only"),
            Line2D([0], [0], color="#b22222", lw=3, linestyle=":", label="Congested ABR1-ABR2"),
        ],
        loc="lower center",
        ncol=2,
        frameon=False,
        fontsize=8,
    )
    ax.set_title("ASHR Congestion Response: Before and After Path")
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
    # Ensure zero values are shown and annotate bar heights for clarity.
    ax.set_ylim(bottom=0)
    for rect in ax.patches:
        height = rect.get_height()
        # Format integers without decimal, floats with up to 2 decimals
        if abs(height - round(height)) < 1e-9:
            label = f"{int(round(height))}"
        else:
            label = f"{height:.2f}"
        ax.annotate(
            label,
            xy=(rect.get_x() + rect.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )
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


def plot_scalability_convergence(rows: list[dict[str, object]], output_dir: str | Path) -> Path:
    output_dir = ensure_dir(output_dir)
    path = output_dir / "scalability_convergence_vs_nodes.png"
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    colors = {
        "RIP": "#4c78a8",
        "OSPF": "#f58518",
        "IS-IS": "#54a24b",
        "BGP": "#e45756",
        "ASHR": "#72b7b2",
    }
    for protocol, group in df.groupby("protocol"):
        group = group.sort_values("node_count")
        ax.plot(
            group["node_count"],
            # prefer seconds column if available
            group["convergence_time_s"] if "convergence_time_s" in group.columns else group["convergence_time_units"],
            marker="o",
            linewidth=2,
            label=protocol,
            color=colors.get(protocol),
        )
    ax.set_title("Scalability Benchmark: Convergence Time vs Node Count")
    ax.set_xlabel("Number of routers")
    ax.set_ylabel("Convergence / recovery time (s)")
    ax.grid(alpha=0.25)
    ax.legend()
    _save(fig, path)
    return path


def plot_control_messages_vs_nodes(rows: list[dict[str, object]], output_dir: str | Path) -> Path:
    output_dir = ensure_dir(output_dir)
    path = output_dir / "control_messages_vs_nodes.png"
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    colors = {
        "RIP": "#4c78a8",
        "OSPF": "#f58518",
        "IS-IS": "#54a24b",
        "BGP": "#e45756",
        "ASHR": "#72b7b2",
    }
    for protocol, group in df.groupby("protocol"):
        group = group.sort_values("node_count")
        ax.plot(
            group["node_count"],
            group["control_messages"],
            marker="o",
            linewidth=2,
            label=protocol,
            color=colors.get(protocol),
        )
    ax.set_title("Control Messages vs Node Count")
    ax.set_xlabel("Number of routers")
    ax.set_ylabel("Control messages")
    ax.grid(alpha=0.25)
    ax.legend()
    _save(fig, path)
    return path


def _router_sort_key(router: str) -> tuple[str, int, str]:
    prefix = "".join(ch for ch in router if not ch.isdigit())
    suffix = "".join(ch for ch in router if ch.isdigit())
    return prefix, int(suffix or 0), router


def _scalable_positions(graph: nx.Graph) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    area_1 = sorted((n for n, data in graph.nodes(data=True) if data["area_id"] == 1), key=_router_sort_key)
    area_2 = sorted((n for n, data in graph.nodes(data=True) if data["area_id"] == 2), key=_router_sort_key)

    def assign(nodes: list[str], x: float) -> None:
        if len(nodes) == 1:
            positions[nodes[0]] = (x, 0.0)
            return
        midpoint = (len(nodes) - 1) / 2
        for index, node in enumerate(nodes):
            positions[node] = (x, midpoint - index)

    assign(area_1, 0.0)
    assign(area_2, 3.0)
    positions["ABR1"] = (1.15, 0.6)
    positions["ABR2"] = (1.85, -0.6)
    return positions


def plot_scalable_topology_examples(graphs: list[nx.Graph], output_dir: str | Path) -> Path:
    output_dir = ensure_dir(output_dir)
    path = output_dir / "scalable_topology_examples.png"
    fig, axes = plt.subplots(1, len(graphs), figsize=(5.2 * len(graphs), 6.2))
    if len(graphs) == 1:
        axes = [axes]

    for ax, graph in zip(axes, graphs):
        positions = _scalable_positions(graph)
        colors = []
        for node in graph.nodes:
            area = graph.nodes[node]["area_id"]
            if area == 0:
                colors.append("#4c78a8")
            elif area == 1:
                colors.append("#59a14f")
            else:
                colors.append("#f28e2b")
        node_size = 190 if graph.number_of_nodes() <= 12 else 85 if graph.number_of_nodes() <= 40 else 52
        nx.draw_networkx_edges(graph, positions, width=0.8, edge_color="#9b9b9b", alpha=0.75, ax=ax)
        nx.draw_networkx_nodes(graph, positions, node_color=colors, node_size=node_size, linewidths=0.4, edgecolors="#222222", ax=ax)

        labels = {"ABR1": "ABR1", "ABR2": "ABR2"}
        source = graph.graph.get("source")
        destination = graph.graph.get("destination")
        if source:
            labels[source] = str(source)
        if destination:
            labels[destination] = str(destination)
        nx.draw_networkx_labels(graph, positions, labels=labels, font_size=7, font_weight="bold", ax=ax)

        ax.set_title(f"{graph.number_of_nodes()} routers / {graph.number_of_edges()} links")
        ax.axis("off")

    fig.suptitle("Scalable Hierarchical Topology Examples", fontsize=14, y=0.98)
    _save(fig, path)
    return path
