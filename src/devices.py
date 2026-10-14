"""
devices.py - Controle de acesso e concorrência em dispositivos.

Contém:
  1. AccessMatrix  - matriz de controle de acesso (processo x dispositivo x permissão)
                     seguindo o princípio do menor privilégio.
  2. Device        - dispositivo protegido por mutex/semáforo, com modo exclusivo.
  3. simulate_queue         - simulação DETERMINÍSTICA (tempo simulado) de fila FIFO em um dispositivo.
  4. race_condition_demo    - demonstração com threads reais: SEM mutex x COM mutex.
  5. threaded_device_demo   - threads disputando o disco; prova que não há sobreposição.

Permissões: R=ler, W=gravar, X=executar, U=utilizar o dispositivo, E=solicitar acesso exclusivo.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

PERMS = ("R", "W", "X", "U", "E")
PERM_NAMES = {"R": "ler", "W": "gravar", "X": "executar", "U": "utilizar", "E": "acesso exclusivo"}
DEVICES = ("disco", "rede", "audio", "log")

# Matriz padrão (menor privilégio) derivada da tabela de processos do enunciado.
DEFAULT_MATRIX: Dict[str, Dict[str, Set[str]]] = {
    "P1": {"rede": {"R", "W", "U"},           "log": {"W"}},                      # monitoramento
    "P2": {"rede": {"R", "W", "U"},           "log": {"W"}},                      # telemetria
    "P3": {"disco": {"R", "W", "U"},          "log": {"W"}},                      # relatórios
    "P4": {"audio": {"W", "X", "U", "E"},     "rede": {"W", "X", "U", "E"},       # alarme crítico
           "log": {"W"}},
    "P5": {"disco": {"R", "W", "X", "U", "E"}, "log": {"W"}},                     # backup
    "P6": {"disco": {"R", "W", "U"},          "rede": {"R", "W", "U"}, "log": {"W"}},  # atualização
}


class AccessDenied(Exception):
    """Levantada quando um processo tenta uma operação não autorizada."""


class AccessMatrix:
    def __init__(self, matrix: Optional[Dict[str, Dict[str, Set[str]]]] = None):
        self.matrix = matrix if matrix is not None else {
            pid: {d: set(p) for d, p in devs.items()} for pid, devs in DEFAULT_MATRIX.items()}

    def allowed(self, pid: str, device: str, perm: str) -> bool:
        return perm in self.matrix.get(pid, {}).get(device, set())

    def check(self, pid: str, device: str, perm: str) -> None:
        if perm not in PERMS:
            raise ValueError(f"Permissão inválida: {perm}")
        if not self.allowed(pid, device, perm):
            raise AccessDenied(f"{pid} NÃO tem permissão '{perm}' ({PERM_NAMES[perm]}) em '{device}'.")

    def render(self) -> str:
        """Tabela: linhas = processos, colunas = dispositivos (permissões concedidas)."""
        pids = sorted(self.matrix)
        w = 12
        head = f"{'Processo':<10}" + "".join(f"{d:^{w}}" for d in DEVICES)
        lines = [head, "-" * len(head)]
        for pid in pids:
            row = f"{pid:<10}"
            for d in DEVICES:
                perms = "".join(p for p in PERMS if p in self.matrix[pid].get(d, set()))
                row += f"{(perms or '-'):^{w}}"
            lines.append(row)
        lines.append("Legenda: R=ler  W=gravar  X=executar  U=utilizar  E=acesso exclusivo  -=sem acesso")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Dispositivo com mutex / semáforo
# --------------------------------------------------------------------------- #
class Device:
    """
    ``capacity`` = número de usuários simultâneos permitidos (semáforo contador).
    capacity=1 equivale a um mutex. O modo exclusivo ('E') captura TODAS as vagas.
    """

    def __init__(self, name: str, capacity: int = 1, matrix: Optional[AccessMatrix] = None):
        self.name = name
        self.capacity = capacity
        self.matrix = matrix
        self._sem = threading.Semaphore(capacity)
        self._gate = threading.Lock()          # impede furar a fila durante um pedido exclusivo
        self.log: List[Tuple[str, str, float, float]] = []   # (pid, op, início, fim)
        self._log_lock = threading.Lock()

    def use(self, pid: str, perm: str, duration: float = 0.05, exclusive: bool = False) -> None:
        if self.matrix is not None:
            self.matrix.check(pid, self.name, perm)
            if exclusive:
                self.matrix.check(pid, self.name, "E")
        slots = self.capacity if exclusive else 1
        with self._gate:                       # entra na fila de pedidos em ordem
            for _ in range(slots):
                self._sem.acquire()
        start = time.perf_counter()
        try:
            time.sleep(duration)               # "usa" o dispositivo
        finally:
            end = time.perf_counter()
            for _ in range(slots):
                self._sem.release()
            with self._log_lock:
                self.log.append((pid, perm + ("*" if exclusive else ""), start, end))

    def overlaps(self) -> int:
        """Conta pares de usos sobrepostos (deve ser 0 quando capacity=1)."""
        ev = sorted(self.log, key=lambda e: e[2])
        return sum(1 for a, b in zip(ev, ev[1:]) if b[2] < a[3])


# --------------------------------------------------------------------------- #
# Simulação determinística da fila (tempo simulado)
# --------------------------------------------------------------------------- #
@dataclass
class Request:
    pid: str
    arrival: int
    duration: int
    perm: str = "W"


def simulate_queue(requests: List[Request], device: str = "disco",
                   matrix: Optional[AccessMatrix] = None):
    """
    Fila FIFO em um dispositivo exclusivo (mutex). Retorna (linhas, negados).
    Cada linha: dict(pid, chegada, inicio, fim, espera). Pedidos sem permissão são recusados.
    """
    matrix = matrix or AccessMatrix()
    granted, denied = [], []
    for rq in sorted(requests, key=lambda r: (r.arrival, r.pid)):
        try:
            matrix.check(rq.pid, device, rq.perm)
            granted.append(rq)
        except AccessDenied as exc:
            denied.append((rq.pid, str(exc)))
    t, rows = 0, []
    for rq in granted:
        start = max(t, rq.arrival)
        end = start + rq.duration
        rows.append({"pid": rq.pid, "chegada": rq.arrival, "inicio": start, "fim": end,
                     "espera": start - rq.arrival})
        t = end
    return rows, denied


def queue_table(rows: List[dict], device: str) -> str:
    head = f"Fila do dispositivo '{device}' (mutex, FIFO)\n{'Proc':<6}{'Chegada':>8}{'Início':>8}{'Fim':>6}{'Espera':>8}"
    lines = [head, "-" * 36]
    for r in rows:
        lines.append(f"{r['pid']:<6}{r['chegada']:>8}{r['inicio']:>8}{r['fim']:>6}{r['espera']:>8}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Demonstrações com threads reais
# --------------------------------------------------------------------------- #
def race_condition_demo(use_mutex: bool, n_threads: int = 5, iterations: int = 200) -> Tuple[int, int]:
    """
    n_threads incrementam um contador compartilhado (ex.: contador do arquivo de log).
    Sem mutex a sequência ler-modificar-gravar é interrompida e há atualizações perdidas.
    Retorna (valor_final, valor_esperado).
    """
    counter = {"v": 0}
    lock = threading.Lock()

    def worker():
        for _ in range(iterations):
            if use_mutex:
                with lock:
                    tmp = counter["v"]
                    time.sleep(0)          # força possível troca de thread
                    counter["v"] = tmp + 1
            else:
                tmp = counter["v"]
                time.sleep(0)              # força possível troca de thread
                counter["v"] = tmp + 1

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter["v"], n_threads * iterations


def threaded_device_demo(pids=("P3", "P5", "P6"), device_name: str = "disco",
                         capacity: int = 1, duration: float = 0.05) -> Device:
    """Threads de processos reais disputando o mesmo dispositivo (protegido por mutex)."""
    matrix = AccessMatrix()
    dev = Device(device_name, capacity=capacity, matrix=matrix)
    threads = [threading.Thread(target=dev.use, args=(pid, "W", duration)) for pid in pids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return dev
