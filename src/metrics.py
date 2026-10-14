"""
metrics.py - Métricas agregadas, justiça/starvation, tabelas em texto e gráficos.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from schedulers import ScheduleResult


# --------------------------------------------------------------------------- #
# Métricas agregadas
# --------------------------------------------------------------------------- #
def averages(res: ScheduleResult) -> Dict[str, float]:
    n = len(res.metrics)
    ms = res.metrics.values()
    return {
        "espera": sum(m.waiting for m in ms) / n,
        "retorno": sum(m.turnaround for m in ms) / n,
        "resposta": sum(m.response for m in ms) / n,
    }


def jain_fairness(res: ScheduleResult) -> float:
    """
    Índice de Jain sobre a 'taxa de progresso' x_i = burst_i / retorno_i
    (fração do tempo no sistema em que o processo de fato usou a CPU).
    Vai de 1/n (injusto) até 1,0 (perfeitamente justo).
    """
    xs = [m.burst / m.turnaround for m in res.metrics.values()]
    return sum(xs) ** 2 / (len(xs) * sum(x * x for x in xs))


def starvation_report(res: ScheduleResult, max_wait: int = 15,
                      max_penalty: float = 2.0) -> List[dict]:
    """
    Marca processos sujeitos a atraso excessivo:
      * espera > ``max_wait`` ut, OU
      * penalidade (espera / burst) >= ``max_penalty``.
    """
    out = []
    for m in res.metrics.values():
        pen = m.waiting / m.burst
        if m.waiting > max_wait or pen >= max_penalty:
            out.append({"pid": m.pid, "espera": m.waiting, "penalidade": round(pen, 2),
                        "prioridade": m.priority})
    return sorted(out, key=lambda d: -d["espera"])


def summary_rows(results: List[ScheduleResult]) -> List[dict]:
    rows = []
    for r in results:
        a = averages(r)
        p4 = r.metrics.get("P4")
        rows.append({
            "algoritmo": r.algorithm,
            "espera": a["espera"], "retorno": a["retorno"], "resposta": a["resposta"],
            "trocas": r.context_switches,
            "alarme_espera": p4.waiting if p4 else None,
            "alarme_resposta": p4.response if p4 else None,
            "jain": jain_fairness(r),
            "starvation": [d["pid"] for d in starvation_report(r)],
        })
    return rows


# --------------------------------------------------------------------------- #
# Texto: Gantt e tabelas
# --------------------------------------------------------------------------- #
def gantt_text(res: ScheduleResult) -> str:
    """Gantt em ASCII: largura de 3 caracteres por unidade de tempo."""
    w = 3
    bar, ticks = "|", ""
    for pid, s, e in res.gantt:
        label = pid or "--"
        bar += label.center(w * (e - s) - 1, " ") + "|"
        ticks += str(s).ljust(w * (e - s))
    ticks += str(res.gantt[-1][2])
    return bar + "\n" + ticks


def metrics_table(res: ScheduleResult) -> str:
    head = (f"{'Proc':<5}{'Cheg':>5}{'Burst':>6}{'Prio':>5}{'Início':>7}{'Fim':>5}"
            f"{'Espera':>8}{'Retorno':>9}{'Resposta':>10}")
    lines = [head, "-" * len(head)]
    for pid in sorted(res.metrics):
        m = res.metrics[pid]
        lines.append(f"{m.pid:<5}{m.arrival:>5}{m.burst:>6}{m.priority:>5}{m.first_start:>7}"
                     f"{m.completion:>5}{m.waiting:>8}{m.turnaround:>9}{m.response:>10}")
    a = averages(res)
    lines.append("-" * len(head))
    lines.append(f"{'MÉDIA':<5}{'':>28}{a['espera']:>8.2f}{a['retorno']:>9.2f}{a['resposta']:>10.2f}")
    return "\n".join(lines)


def comparison_table(results: List[ScheduleResult]) -> str:
    head = (f"{'Algoritmo':<40}{'Espera':>8}{'Retorno':>9}{'Resp.':>7}{'Trocas':>7}"
            f"{'P4 esp.':>8}{'P4 resp.':>9}{'Jain':>7}")
    lines = [head, "-" * len(head)]
    for r in summary_rows(results):
        lines.append(f"{r['algoritmo']:<40}{r['espera']:>8.2f}{r['retorno']:>9.2f}{r['resposta']:>7.2f}"
                     f"{r['trocas']:>7}{r['alarme_espera']:>8}{r['alarme_resposta']:>9}{r['jain']:>7.3f}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Gráficos (matplotlib é opcional)
# --------------------------------------------------------------------------- #
def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:          # pragma: no cover
        return None


def short_label(name: str) -> str:
    """Rótulo curto para o eixo X dos gráficos."""
    n = name.replace("Prioridade (não preemptivo)", "Prioridade\n(não preempt.)")
    n = n.replace("Prioridade (preemptivo, aging=", "Prioridade preempt.\n+ aging (").replace("Prioridade (preemptivo)", "Prioridade\n(preemptivo)")
    return n.replace("Round Robin (", "Round Robin\n(")


COLORS = {"P1": "#1f77b4", "P2": "#2ca02c", "P3": "#ff7f0e", "P4": "#d62728",
          "P5": "#9467bd", "P6": "#8c564b"}


def plot_gantt(results: List[ScheduleResult], path: str) -> Optional[str]:
    plt = _plt()
    if plt is None:
        return None
    n = len(results)
    fig, axes = plt.subplots(n, 1, figsize=(11, 1.15 * n + 0.8), sharex=True)
    axes = [axes] if n == 1 else list(axes)
    end = max(r.gantt[-1][2] for r in results)
    for ax, r in zip(axes, results):
        for pid, s, e in r.gantt:
            if pid is None:
                continue
            ax.barh(0, e - s, left=s, color=COLORS.get(pid, "gray"), edgecolor="white", height=0.7)
            ax.text((s + e) / 2, 0, pid, ha="center", va="center", color="white",
                    fontsize=8, weight="bold")
        ax.set_yticks([])
        ax.set_ylabel(r.algorithm, rotation=0, ha="right", va="center", fontsize=8)
        ax.set_xlim(0, end)
    axes[-1].set_xlabel("Tempo (ut)")
    axes[-1].set_xticks(range(0, end + 1, 2))
    fig.suptitle("Diagramas de Gantt - comparação dos escalonadores", fontsize=11)
    fig.tight_layout(rect=(0.13, 0, 1, 0.97))
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _bar(ax, labels, series: Dict[str, List[float]], title, ylabel, fmt="{:.1f}"):
    n = len(series)
    width = 0.8 / n
    for i, (name, vals) in enumerate(series.items()):
        xs = [x - 0.4 + width * (i + 0.5) for x in range(len(labels))]
        bars = ax.bar(xs, vals, width, label=name)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(v),
                    ha="center", va="bottom", fontsize=7)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_title(title, fontsize=10)
    ax.set_ylabel(ylabel)
    if n > 1:
        ax.legend(fontsize=8)


def plot_scheduling_comparison(results: List[ScheduleResult], path: str) -> Optional[str]:
    plt = _plt()
    if plt is None:
        return None
    rows = summary_rows(results)
    labels = [short_label(r["algoritmo"]) for r in rows]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    _bar(axes[0], labels, {"Espera": [r["espera"] for r in rows],
                           "Retorno": [r["retorno"] for r in rows],
                           "Resposta": [r["resposta"] for r in rows]},
         "Tempos médios por algoritmo", "ut")
    _bar(axes[1], labels, {"Trocas de contexto": [r["trocas"] for r in rows]},
         "Trocas de contexto", "quantidade", "{:.0f}")
    _bar(axes[2], labels, {"Índice de Jain": [r["jain"] for r in rows]},
         "Justiça (Jain; 1,0 = perfeito)", "índice", "{:.2f}")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def plot_alarm(results: List[ScheduleResult], path: str) -> Optional[str]:
    plt = _plt()
    if plt is None:
        return None
    rows = summary_rows(results)
    labels = [short_label(r["algoritmo"]) for r in rows]
    fig, ax = plt.subplots(figsize=(11, 4.4))
    _bar(ax, labels, {"Espera P4": [r["alarme_espera"] for r in rows],
                      "Resposta P4": [r["alarme_resposta"] for r in rows]},
         "Processo crítico P4 (alarme): espera e resposta", "ut", "{:.0f}")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def plot_memory(mem_results, path: str) -> Optional[str]:
    plt = _plt()
    if plt is None:
        return None
    labels = [m.algorithm for m in mem_results]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, (title, vals, color, fmt) in zip(axes, [
        ("Page faults", [m.faults for m in mem_results], "#d62728", "{:.0f}"),
        ("Page hits", [m.hits for m in mem_results], "#2ca02c", "{:.0f}"),
        ("Taxa de faltas (%)", [m.fault_rate * 100 for m in mem_results], "#ff7f0e", "{:.1f}"),
    ]):
        bars = ax.bar(labels, vals, color=color)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(v),
                    ha="center", va="bottom", fontsize=9)
        ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def plot_frames_sweep(sweep: Dict[str, List[int]], frames_range: List[int], path: str) -> Optional[str]:
    plt = _plt()
    if plt is None:
        return None
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, vals in sweep.items():
        ax.plot(frames_range, vals, marker="o", label=name)
    ax.set_xlabel("Quantidade de frames")
    ax.set_ylabel("Page faults")
    ax.set_title("Page faults x número de frames", fontsize=10)
    ax.set_xticks(frames_range)
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
