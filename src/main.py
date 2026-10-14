"""
main.py - Ponto de entrada do KernelLab.

Fluxo: entrada dos processos -> escalonamento -> métricas -> memória ->
       dispositivos -> comparação dos resultados.

Exemplos:
    python src/main.py                          # roda tudo com data/processes.json
    python src/main.py --quantum 4              # muda o quantum do Round Robin
    python src/main.py --frames 3 --refs 7,0,1,2,0,3,0,4,2,3
    python src/main.py --config meu_cenario.json --save-report docs/resultados.md
    python src/main.py --only sched|memory|devices
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import devices as dv      # noqa: E402
import memory as mem      # noqa: E402
import metrics as mt      # noqa: E402
import schedulers as sc   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fence(text: str) -> str:
    return "```\n" + text + "\n```"


# --------------------------------------------------------------------------- #
# Seções
# --------------------------------------------------------------------------- #
def section_scheduling(procs, quantum, img_dir):
    out = ["## Etapa 1 - Escalonamento da CPU", ""]
    results = sc.run_all(procs, quantum)
    for r in results:
        out += [f"### {r.algorithm}", "",
                f"Ordem de execução (1ª vez na CPU): {' -> '.join(r.execution_order)}", "",
                "Diagrama de Gantt:", fence(mt.gantt_text(r)), "",
                fence(mt.metrics_table(r)), "",
                f"Trocas de contexto: {r.context_switches}"]
        sv = mt.starvation_report(r)
        if sv:
            txt = "; ".join(f"{d['pid']} (espera {d['espera']} ut, penalidade {d['penalidade']}x)" for d in sv)
            out.append(f"Atraso excessivo / risco de starvation: {txt}")
        else:
            out.append("Atraso excessivo / risco de starvation: nenhum processo acima do limite.")
        out.append("")

    out += ["## Etapa 2 - Comparação dos escalonadores", "", fence(mt.comparison_table(results)), ""]
    rows = mt.summary_rows(results)
    required = rows[:4]   # FCFS, SJF, RR, Prioridade (NP) - os 4 obrigatórios
    best = lambda lst, k, mx=False: (max if mx else min)(lst, key=lambda r: r[k])
    out += [
        "Respostas calculadas automaticamente:", "",
        f"- Menor tempo médio de espera (4 obrigatórios): {best(required,'espera')['algoritmo']} "
        f"({best(required,'espera')['espera']:.2f} ut); considerando também as variantes: "
        f"{best(rows,'espera')['algoritmo']} ({best(rows,'espera')['espera']:.2f} ut).",
        f"- Melhor tempo médio de resposta: {best(rows,'resposta')['algoritmo']} "
        f"({best(rows,'resposta')['resposta']:.2f} ut).",
        f"- Melhor tratamento do alarme (P4): {best(rows,'alarme_resposta')['algoritmo']} "
        f"(resposta {best(rows,'alarme_resposta')['alarme_resposta']} ut, "
        f"espera {best(rows,'alarme_resposta')['alarme_espera']} ut).",
        f"- Distribuição mais justa (Jain): {best(rows,'jain',True)['algoritmo']} "
        f"({best(rows,'jain',True)['jain']:.3f}).",
        f"- Mais trocas de contexto: {best(rows,'trocas',True)['algoritmo']} "
        f"({best(rows,'trocas',True)['trocas']}).",
        "- Maior risco de starvation: escalonamento por prioridade (e SJF) sem aging - "
        "processos longos/de baixa prioridade (P5, P3) podem ser adiados indefinidamente se "
        "continuarem chegando processos mais prioritários/curtos; com aging o atraso diminui.",
        "",
    ]
    # --- cenário de estresse: starvation real ---
    s_procs = sc.stress_scenario()
    plain = sc.priority(s_procs, preemptive=True)
    aged = sc.priority(s_procs, preemptive=True, aging_interval=3)
    out += ["### Cenário de estresse: starvation com chegadas contínuas", "",
            "BKP (prioridade 5, burst 4) chega em t=1; a cada 3 ut chega um processo de prioridade 1 (burst 3), "
            "mantendo a CPU saturada.", "",
            f"- Prioridade preemptiva SEM aging: BKP espera {plain.metrics['BKP'].waiting} ut "
            f"(conclui em t={plain.metrics['BKP'].completion}).",
            f"- Prioridade preemptiva COM aging (3 ut): BKP espera {aged.metrics['BKP'].waiting} ut "
            f"(conclui em t={aged.metrics['BKP'].completion}).", ""]
    imgs = []
    if img_dir:
        os.makedirs(img_dir, exist_ok=True)
        for fn, path in [(mt.plot_gantt, "gantt.png"), (mt.plot_scheduling_comparison, "comparacao_escalonadores.png"),
                         (mt.plot_alarm, "alarme_p4.png")]:
            p = fn(results, os.path.join(img_dir, path))
            if p:
                imgs.append(path)
    return out, results, imgs


def section_memory(refs, n_frames, img_dir):
    out = ["## Etapa 3 - Gerenciamento de memória", "",
           f"Frames: {n_frames} | Referências ({len(refs)}): {', '.join(map(str, refs))}", ""]
    results = mem.run_all(refs, n_frames)
    for r in results:
        out += [f"### {r.algorithm}", "", fence(mem.steps_table(r)), ""]
    best = min(results, key=lambda r: r.faults)
    out += ["### Comparação", "",
            "| Algoritmo | Page hits | Page faults | Taxa de faltas |", "|---|---|---|---|"]
    out += [f"| {r.algorithm} | {r.hits} | {r.faults} | {r.fault_rate:.1%} |" for r in results]
    practical = min(results[:2], key=lambda r: r.faults)      # FIFO ou LRU (Optimal não é implementável)
    out += ["", f"Melhor resultado: **{best.algorithm}** ({best.faults} faltas) - referência teórica.",
            f"Melhor algoritmo implementável: **{practical.algorithm}** ({practical.faults} faltas)."]
    f, l, o = results
    out += [
        "",
        f"Justificativa: o Optimal ({o.faults} faltas) enxerga o futuro e descarta a página cujo próximo uso é "
        f"o mais distante - é um limite inferior, impossível de implementar na prática. O LRU ({l.faults}) "
        f"aproxima o Optimal usando o passado recente como previsão (localidade temporal). O FIFO ({f.faults}) "
        f"ignora o uso e pode descartar páginas muito acessadas só por serem antigas.", "",
    ]
    imgs = []
    if img_dir:
        p = mt.plot_memory(results, os.path.join(img_dir, "memoria.png"))
        if p:
            imgs.append("memoria.png")
        rng = list(range(1, max(refs) + 2)) if refs else [1]
        p = mt.plot_frames_sweep(mem.sweep_frames(refs, rng), rng, os.path.join(img_dir, "frames_sweep.png"))
        if p:
            imgs.append("frames_sweep.png")
    return out, results, imgs


def section_devices():
    out = ["## Etapa 4 - Controle de dispositivos", "",
           "### Matriz de controle de acesso", "", fence(dv.AccessMatrix().render()), ""]
    # tentativa não autorizada
    m = dv.AccessMatrix()
    out += ["### Verificação de acessos", ""]
    for pid, d, p in [("P1", "disco", "W"), ("P3", "rede", "U"), ("P2", "audio", "U"), ("P4", "audio", "E")]:
        try:
            m.check(pid, d, p)
            out.append(f"- {pid} -> {d} ({p}): PERMITIDO")
        except dv.AccessDenied as exc:
            out.append(f"- {pid} -> {d} ({p}): NEGADO - {exc}")
    # fila simulada
    reqs = [dv.Request("P3", 2, 4), dv.Request("P5", 3, 5), dv.Request("P6", 4, 3), dv.Request("P1", 4, 2)]
    rows, denied = dv.simulate_queue(reqs, "disco")
    out += ["", "### Fila de solicitações concorrentes ao disco (tempo simulado)", "",
            "P3, P5, P6 e P1 pedem o disco quase juntos; P1 não tem permissão e é recusado.", "",
            fence(dv.queue_table(rows, "disco")), ""]
    for pid, msg in denied:
        out.append(f"- Recusado: {msg}")
    # threads reais
    final, expected = dv.race_condition_demo(False)
    final_m, _ = dv.race_condition_demo(True)
    out += ["", "### Exclusão mútua com threads reais", "",
            f"- SEM mutex: contador final = {final} (esperado {expected}) -> "
            + ("condição de corrida (atualizações perdidas)." if final != expected else
               "nenhuma perda nesta execução (a corrida é não determinística)."),
            f"- COM mutex: contador final = {final_m} (esperado {expected}) -> correto.", ""]
    dev = dv.threaded_device_demo()
    base = min(e[2] for e in dev.log)
    out.append("Uso do disco por 3 threads (mutex, capacidade 1) - intervalos em ms:")
    out.append(fence("\n".join(f"{pid}  [{(s-base)*1000:6.0f} -> {(e-base)*1000:6.0f}]" for pid, _, s, e in
                               sorted(dev.log, key=lambda x: x[2]))))
    out.append(f"Sobreposições detectadas: {dev.overlaps()} (esperado: 0).")
    out.append("")
    return out


def recommendation(results) -> str:
    by = {r.algorithm: r for r in results}
    fc, rr = by["FCFS"], next(r for r in results if r.algorithm.startswith("Round Robin"))
    pp = by["Prioridade (preemptivo)"]
    ag = next(r for r in results if "aging" in r.algorithm)
    st = sc.stress_scenario()
    sp, sa = sc.priority(st, True), sc.priority(st, True, aging_interval=3)
    a = lambda r: mt.averages(r)["espera"]
    f = lambda x: f"{x:.2f}".replace(".", ",")
    return f"""## Recomendação final

**Política recomendada: escalonamento por prioridade PREEMPTIVO, com aging como proteção contra starvation**
(e Round Robin apenas entre processos de mesma prioridade, se houver).

- **Criticidade:** o alarme (P4) recebe a CPU assim que chega (resposta {pp.metrics['P4'].response} ut). FCFS o faz
  esperar {fc.metrics['P4'].waiting} ut e o Round Robin {rr.metrics['P4'].waiting} ut - inaceitável para um alarme clínico.
- **Desempenho:** espera média de {f(a(pp))} ut, a menor entre todas as políticas testadas (FCFS {f(a(fc))}; RR {f(a(rr))}).
- **Justiça / starvation:** o RR é o mais justo (Jain {f(mt.jain_fairness(rr))}), mas atrasa o alarme em {rr.metrics['P4'].waiting} ut.
  O aging tem custo no cenário base (espera média {f(a(pp))} -> {f(a(ag))} ut; trocas de contexto {pp.context_switches} -> {ag.context_switches}),
  mas no cenário de estresse reduz a espera do processo de baixa prioridade de {sp.metrics['BKP'].waiting} para {sa.metrics['BKP'].waiting} ut,
  evitando starvation real. Com `aging_floor=1`, a classe 0 fica reservada ao alarme (P4 continua com espera {ag.metrics['P4'].waiting}). O intervalo deve ser calibrado.
- **Memória:** LRU (ou uma aproximação barata, como o algoritmo do relógio), pois reduz as faltas em relação ao FIFO.
- **Dispositivos:** manter a matriz de menor privilégio e mutex/semáforo; acesso exclusivo restrito a P4 (áudio/rede) e P5 (disco).

**Limitações que permanecem:** 1 CPU e burst conhecido de antemão (SJF/prioridade dependem disso); sem custo de troca de
contexto nem E/S bloqueante; sem tratamento de inversão de prioridade (um processo de baixa prioridade segurando o mutex que
o alarme precisa exigiria *priority inheritance*); sequência de páginas fixa e curta; sem garantias de tempo real rígido
(deadlines, EDF/RMS)."""


def render(procs, quantum, refs, n_frames, img_dir, only=None):
    out = ["# KernelLab - Resultados da simulação", ""]
    out += ["## Entrada", "", "| Proc | Função | Chegada | Burst | Prioridade | Memória | Dispositivos |",
            "|---|---|---|---|---|---|---|"]
    out += [f"| {p.pid} | {p.name} | {p.arrival} | {p.burst} | {p.priority} | {p.memory_mb} MB | "
            f"{', '.join(p.devices)} |" for p in procs]
    out += ["", f"Quantum do Round Robin: {quantum}", ""]
    imgs = []
    if only in (None, "sched"):
        o, _, i = section_scheduling(procs, quantum, img_dir)
        out += o
        imgs += i
    if only in (None, "memory"):
        o, _, i = section_memory(refs, n_frames, img_dir)
        out += o
        imgs += i
    if only in (None, "devices"):
        out += section_devices()
    if only is None:
        out += [recommendation(sc.run_all(procs, quantum)), ""]
    if imgs:
        out += ["## Etapa 5 - Gráficos gerados", ""] + [f"![{n}](img/{n})" for n in imgs] + [""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="KernelLab - simulador de CPU, memória e dispositivos")
    ap.add_argument("--config", default=os.path.join(ROOT, "data", "processes.json"))
    ap.add_argument("--quantum", type=int, help="quantum do Round Robin (sobrescreve o JSON)")
    ap.add_argument("--frames", type=int, help="quantidade de frames (sobrescreve o JSON)")
    ap.add_argument("--refs", help="sequência de páginas separada por vírgula, ex.: 1,2,3,4")
    ap.add_argument("--only", choices=["sched", "memory", "devices"])
    ap.add_argument("--no-charts", action="store_true", help="não gera gráficos PNG")
    ap.add_argument("--img-dir", default=os.path.join(ROOT, "docs", "img"))
    ap.add_argument("--save-report", metavar="ARQUIVO.md", help="salva a saída em Markdown")
    a = ap.parse_args(argv)

    cfg = sc.load_config(a.config)
    quantum = a.quantum or cfg["quantum"]
    frames = a.frames or cfg["frames"]
    refs = [int(x) for x in a.refs.split(",")] if a.refs else cfg["references"]

    text = render(cfg["processes"], quantum, refs, frames, None if a.no_charts else a.img_dir, a.only)
    print(text)
    if a.save_report:
        os.makedirs(os.path.dirname(os.path.abspath(a.save_report)), exist_ok=True)
        with open(a.save_report, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"\n[Relatório salvo em {a.save_report}]")


if __name__ == "__main__":
    main()
