"""
schedulers.py - Algoritmos de escalonamento de CPU do KernelLab.

Todos os algoritmos recebem uma lista de ``Process`` e devolvem um
``ScheduleResult``. Os dados (processos, quantum, aging) entram como
parâmetros: nenhuma lógica precisa ser alterada para mudar o cenário.

Convenções
----------
* Tempo discreto, inteiro (unidades de tempo - ut).
* Menor número de prioridade = MAIOR prioridade.
* Desempates: chegada mais cedo e, depois, ordem do PID.
* Trocas de contexto = vezes em que a CPU passa de um processo para OUTRO
  processo diferente (o despacho inicial e os intervalos ociosos não contam).
* No Round Robin, se um processo chega exatamente no instante em que um
  quantum termina, ele entra na fila ANTES do processo preemptado.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Process:
    pid: str
    arrival: int
    burst: int
    priority: int = 0
    memory_mb: int = 0
    devices: Tuple[str, ...] = ()
    name: str = ""


@dataclass
class ProcessMetrics:
    pid: str
    arrival: int
    burst: int
    priority: int
    first_start: int
    completion: int
    waiting: int       # tempo de espera  = retorno - burst
    turnaround: int    # tempo de retorno = conclusão - chegada
    response: int      # tempo de resposta = 1a execução - chegada


@dataclass
class ScheduleResult:
    algorithm: str
    gantt: List[Tuple[Optional[str], int, int]]   # (pid | None=ocioso, início, fim)
    metrics: Dict[str, ProcessMetrics]
    context_switches: int
    execution_order: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Entrada de dados
# --------------------------------------------------------------------------- #
def load_config(path: str) -> dict:
    """Lê o JSON de entrada e devolve {'processes', 'quantum', 'frames', 'references'}."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    procs = [
        Process(
            pid=p["pid"], arrival=int(p["chegada"]), burst=int(p["burst"]),
            priority=int(p["prioridade"]), memory_mb=int(p.get("memoria_mb", 0)),
            devices=tuple(p.get("dispositivos", [])), name=p.get("funcao", ""),
        )
        for p in raw["processos"]
    ]
    mem = raw.get("memoria", {})
    return {
        "processes": procs,
        "quantum": int(raw.get("quantum", 3)),
        "frames": int(mem.get("frames", 4)),
        "references": list(mem.get("referencias", [])),
    }


# --------------------------------------------------------------------------- #
# Funções auxiliares
# --------------------------------------------------------------------------- #
def _validate(processes: List[Process]) -> None:
    if not processes:
        raise ValueError("A lista de processos está vazia.")
    if len({p.pid for p in processes}) != len(processes):
        raise ValueError("PIDs duplicados.")
    for p in processes:
        if p.burst <= 0:
            raise ValueError(f"{p.pid}: burst deve ser > 0.")
        if p.arrival < 0:
            raise ValueError(f"{p.pid}: chegada deve ser >= 0.")


def _merge(gantt: List[Tuple[Optional[str], int, int]]):
    """Junta fatias consecutivas do mesmo processo."""
    merged: List[list] = []
    for pid, s, e in gantt:
        if merged and merged[-1][0] == pid and merged[-1][2] == s:
            merged[-1][2] = e
        else:
            merged.append([pid, s, e])
    return [tuple(m) for m in merged]


def _finalize(name: str, processes: List[Process], gantt) -> ScheduleResult:
    gantt = _merge(gantt)
    first: Dict[str, int] = {}
    last: Dict[str, int] = {}
    for pid, s, e in gantt:
        if pid is None:
            continue
        first.setdefault(pid, s)
        last[pid] = e
    metrics = {}
    for p in processes:
        completion = last[p.pid]
        tat = completion - p.arrival
        metrics[p.pid] = ProcessMetrics(
            pid=p.pid, arrival=p.arrival, burst=p.burst, priority=p.priority,
            first_start=first[p.pid], completion=completion,
            waiting=tat - p.burst, turnaround=tat, response=first[p.pid] - p.arrival,
        )
    busy = [g for g in gantt if g[0] is not None]
    switches = sum(1 for a, b in zip(busy, busy[1:]) if a[0] != b[0])
    order: List[str] = []
    for pid, _, _ in busy:
        if pid not in order:
            order.append(pid)
    return ScheduleResult(name, gantt, metrics, switches, order)


def _non_preemptive(name: str, processes: List[Process], key) -> ScheduleResult:
    """Modelo genérico não preemptivo: escolhe o próximo pelo menor ``key``."""
    _validate(processes)
    pending = sorted(processes, key=lambda p: (p.arrival, p.pid))
    t, gantt = 0, []
    while pending:
        ready = [p for p in pending if p.arrival <= t]
        if not ready:
            nxt = min(p.arrival for p in pending)
            gantt.append((None, t, nxt))
            t = nxt
            continue
        chosen = min(ready, key=key)
        pending.remove(chosen)
        gantt.append((chosen.pid, t, t + chosen.burst))
        t += chosen.burst
    return _finalize(name, processes, gantt)


# --------------------------------------------------------------------------- #
# Algoritmos
# --------------------------------------------------------------------------- #
def fcfs(processes: List[Process]) -> ScheduleResult:
    """First Come, First Served: ordem de chegada, sem preempção."""
    return _non_preemptive("FCFS", processes, key=lambda p: (p.arrival, p.pid))


def sjf(processes: List[Process]) -> ScheduleResult:
    """Shortest Job First (não preemptivo): menor burst entre os prontos."""
    return _non_preemptive("SJF", processes, key=lambda p: (p.burst, p.arrival, p.pid))


def round_robin(processes: List[Process], quantum: int = 3) -> ScheduleResult:
    """Round Robin com fatia de tempo ``quantum``."""
    if quantum <= 0:
        raise ValueError("quantum deve ser > 0.")
    _validate(processes)
    arrivals = deque(sorted(processes, key=lambda p: (p.arrival, p.pid)))
    remaining = {p.pid: p.burst for p in processes}
    queue: deque = deque()
    t, gantt = 0, []

    def admit(now: int):
        while arrivals and arrivals[0].arrival <= now:
            queue.append(arrivals.popleft())

    admit(t)
    while queue or arrivals:
        if not queue:
            nxt = arrivals[0].arrival
            gantt.append((None, t, nxt))
            t = nxt
            admit(t)
            continue
        proc = queue.popleft()
        run = min(quantum, remaining[proc.pid])
        gantt.append((proc.pid, t, t + run))
        t += run
        remaining[proc.pid] -= run
        admit(t)                       # chegadas no fim do quantum entram antes
        if remaining[proc.pid] > 0:
            queue.append(proc)
    return _finalize(f"Round Robin (q={quantum})", processes, gantt)


def priority(processes: List[Process], preemptive: bool = False,
             aging_interval: Optional[int] = None, aging_floor: int = 1) -> ScheduleResult:
    """
    Escalonamento por prioridade (menor número = maior prioridade).

    preemptive      : se True, um processo mais prioritário que chega toma a CPU.
    aging_interval  : se informado, a cada ``aging_interval`` ut esperando na fila
                      de prontos o processo ganha 1 nível de prioridade (anti-starvation).
    aging_floor     : menor número (maior prioridade) que o aging pode alcançar. Com o
                      padrão 1, a classe 0 fica reservada a processos críticos (ex.: alarme),
                      que nunca são ultrapassados por um processo "envelhecido".
    """
    _validate(processes)
    remaining = {p.pid: p.burst for p in processes}
    waiting_since = {p.pid: p.arrival for p in processes}   # desde quando espera
    state = {"running": None, "locked": 0}                  # 'locked' = prioridade efetiva ao despachar

    def eff(p: Process, now: int) -> int:
        """Prioridade efetiva: a promovida por aging vale enquanto o processo executa."""
        if state["running"] is p:
            return state["locked"]
        bonus = (now - waiting_since[p.pid]) // aging_interval if aging_interval else 0
        return max(p.priority - bonus, min(p.priority, aging_floor))

    def pick(now: int):
        ready = [p for p in processes if remaining[p.pid] > 0 and p.arrival <= now]
        if not ready:
            return None
        return min(ready, key=lambda p: (eff(p, now), p.arrival, p.pid))

    t, gantt = 0, []
    total = sum(remaining.values())
    done = 0
    while done < total:
        running = state["running"]
        chosen = pick(t) if (running is None or preemptive) else running
        if chosen is None:                       # CPU ociosa até a próxima chegada
            nxt = min(p.arrival for p in processes if remaining[p.pid] > 0 and p.arrival > t)
            gantt.append((None, t, nxt))
            t = nxt
            continue
        if chosen is not running:
            if running is not None and remaining[running.pid] > 0:
                waiting_since[running.pid] = t   # preemptado: volta a esperar (prioridade base)
            state["locked"] = eff(chosen, t)     # congela a prioridade com que foi despachado
            state["running"] = chosen
            waiting_since[chosen.pid] = t
        gantt.append((chosen.pid, t, t + 1))
        t += 1
        remaining[chosen.pid] -= 1
        done += 1
        if remaining[chosen.pid] == 0:
            state["running"] = None
    label = "Prioridade (" + ("preemptivo" if preemptive else "não preemptivo")
    label += f", aging={aging_interval})" if aging_interval else ")"
    return _finalize(label, processes, gantt)


def run_all(processes: List[Process], quantum: int = 3,
            aging_interval: Optional[int] = 5) -> List[ScheduleResult]:
    """Executa os 4 algoritmos obrigatórios + 2 variantes de prioridade (bônus)."""
    results = [
        fcfs(processes),
        sjf(processes),
        round_robin(processes, quantum),
        priority(processes, preemptive=False),
        priority(processes, preemptive=True),
    ]
    if aging_interval:
        results.append(priority(processes, preemptive=True, aging_interval=aging_interval))
    return results


def stress_scenario(n_high: int = 8) -> List[Process]:
    """
    Cenário de estresse para demonstrar starvation: um processo de baixa prioridade (BKP)
    chega logo no início, mas processos de alta prioridade chegam continuamente
    (um a cada 3 ut, com burst 3), mantendo a CPU 100% ocupada.
    """
    procs = [Process("BKP", arrival=1, burst=4, priority=5, name="Backup (baixa prioridade)")]
    procs += [Process(f"H{i+1}", arrival=3 * i, burst=3, priority=1, name="Alta prioridade")
              for i in range(n_high)]
    return procs
