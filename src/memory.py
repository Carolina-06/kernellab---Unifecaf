"""
memory.py - Algoritmos de substituição de páginas: FIFO, LRU e Optimal.

Cada algoritmo devolve um ``MemoryResult`` com o estado dos frames após
cada referência, hits, faults e taxa de faltas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence


@dataclass
class Step:
    ref: int
    frames: List[Optional[int]]      # estado dos frames após a referência (None = vazio)
    hit: bool
    victim: Optional[int] = None     # página removida (se houve substituição)


@dataclass
class MemoryResult:
    algorithm: str
    n_frames: int
    steps: List[Step] = field(default_factory=list)

    @property
    def hits(self) -> int:
        return sum(s.hit for s in self.steps)

    @property
    def faults(self) -> int:
        return len(self.steps) - self.hits

    @property
    def fault_rate(self) -> float:
        return self.faults / len(self.steps) if self.steps else 0.0


def _run(name: str, refs: Sequence[int], n_frames: int, choose_victim) -> MemoryResult:
    """
    Laço comum a todas as políticas. ``choose_victim`` devolve o ÍNDICE do frame
    a substituir quando não há frame livre.
    """
    if n_frames <= 0:
        raise ValueError("A quantidade de frames deve ser > 0.")
    frames: List[Optional[int]] = [None] * n_frames
    res = MemoryResult(name, n_frames)
    state: dict = {"loaded": {}, "last_use": {}}
    for i, page in enumerate(refs):
        state["last_use"][page] = i
        if page in frames:
            res.steps.append(Step(page, list(frames), True))
            continue
        victim = None
        if None in frames:                          # ainda há frame livre
            idx = frames.index(None)
        else:
            idx = choose_victim(frames, i, state, refs)
            victim = frames[idx]
        frames[idx] = page
        state["loaded"][page] = i
        res.steps.append(Step(page, list(frames), False, victim))
    return res


def fifo(refs: Sequence[int], n_frames: int = 4) -> MemoryResult:
    """FIFO: remove a página que está há mais tempo na memória."""
    def victim(frames, i, st, refs):
        return min(range(len(frames)), key=lambda k: st["loaded"][frames[k]])
    return _run("FIFO", refs, n_frames, victim)


def lru(refs: Sequence[int], n_frames: int = 4) -> MemoryResult:
    """LRU: remove a página menos recentemente usada."""
    def victim(frames, i, st, refs):
        return min(range(len(frames)), key=lambda k: st["last_use"][frames[k]])
    return _run("LRU", refs, n_frames, victim)


def optimal(refs: Sequence[int], n_frames: int = 4) -> MemoryResult:
    """Ótimo (Belady): remove a página cujo próximo uso é o mais distante (ou nunca)."""
    def victim(frames, i, st, refs):
        def next_use(page):
            try:
                return refs.index(page, i + 1)
            except ValueError:
                return float("inf")
        return max(range(len(frames)), key=lambda k: (next_use(frames[k]), -k))
    refs = list(refs)
    return _run("Optimal", refs, n_frames, victim)


def run_all(refs: Sequence[int], n_frames: int = 4) -> List[MemoryResult]:
    return [fifo(refs, n_frames), lru(refs, n_frames), optimal(refs, n_frames)]


def sweep_frames(refs: Sequence[int], frames_range: Sequence[int]):
    """Page faults de cada algoritmo para vários tamanhos de memória."""
    out = {"FIFO": [], "LRU": [], "Optimal": []}
    for n in frames_range:
        for r in run_all(refs, n):
            out[r.algorithm].append(r.faults)
    return out


def steps_table(res: MemoryResult) -> str:
    n = res.n_frames
    head = f"{'#':>3} {'Ref':>3}  " + " ".join(f"F{k+1:<2}" for k in range(n)) + "  Resultado"
    lines = [head, "-" * (len(head) + 14)]
    for i, s in enumerate(res.steps, 1):
        cells = " ".join(f"{(str(f) if f is not None else '-'):<3}" for f in s.frames)
        status = "HIT" if s.hit else "FAULT" + (f" (sai {s.victim})" if s.victim is not None else "")
        lines.append(f"{i:>3} {s.ref:>3}  {cells}  {status}")
    lines.append(f"Hits={res.hits}  Faults={res.faults}  Taxa de faltas={res.fault_rate:.1%}")
    return "\n".join(lines)
