# KernelLab — Simulador de Gerenciamento de CPU, Memória e Dispositivos

Simulador em Python que reproduz decisões de um sistema operacional multitarefa (escalonamento de CPU,
substituição de páginas e controle de acesso a dispositivos) para o cenário da **MedControl Systems**.
Projeto da disciplina de **Sistemas Operacionais** (UniFECAF).

---

## 1. Problema e objetivo

A MedControl monitora equipamentos médicos conectados. O servidor executa ao mesmo tempo monitoramento cardíaco,
telemetria, relatórios, alarme crítico, backup e atualização de dados, e apresenta: atraso nos alarmes, aumento do
tempo de resposta, disputa por CPU, muitas faltas de página, processos de baixa prioridade esperando demais,
concorrência em dispositivos e risco de acesso não autorizado a recursos críticos.

**Objetivo:** construir um simulador (não um SO completo) que reproduza as decisões do SO e permita **comparar
algoritmos** de escalonamento, substituição de páginas e controle de acesso, recomendando a política mais adequada.

Fluxo do simulador:

```
Entrada dos processos → escalonamento da CPU → métricas → gerenciamento da memória
                      → controle dos dispositivos → comparação dos resultados
```

## 2. Arquitetura

```
kernellab/
├── src/
│   ├── main.py         # CLI: orquestra o fluxo, imprime/salva resultados e gera gráficos
│   ├── schedulers.py   # Process, FCFS, SJF, Round Robin, Prioridade (+ aging), carga do JSON
│   ├── memory.py       # FIFO, LRU, Optimal, varredura por nº de frames
│   ├── devices.py      # Matriz de acesso, Device (mutex/semáforo), fila, demos com threads
│   └── metrics.py      # Médias, índice de Jain, starvation, tabelas, Gantt ASCII e gráficos
├── data/processes.json # Processos, quantum, frames e sequência de páginas (entrada editável)
├── tests/              # 37 testes unittest (valores calculados à mão)
├── docs/               # resultados.md (saída completa), img/ (gráficos) e relatório
├── requirements.txt
└── README.md
```

Os algoritmos são **funções puras**: recebem dados (processos, quantum, frames, referências) como parâmetros e
devolvem objetos de resultado. Trocar o cenário **não exige alterar a lógica** — basta editar o JSON ou usar
as opções de linha de comando.

## 3. Algoritmos implementados

| Módulo | Algoritmo | Observações |
|---|---|---|
| CPU | **FCFS** | Não preemptivo, ordem de chegada |
| CPU | **SJF** | Não preemptivo, menor burst entre os prontos |
| CPU | **Round Robin** | Quantum configurável (padrão 3); chegada no fim do quantum entra antes do preemptado |
| CPU | **Prioridade** | Menor número = maior prioridade. Versões **não preemptiva** (principal) e **preemptiva** (bônus), e **preemptiva + aging** (bônus, `aging_floor=1` reserva a classe 0 ao alarme) |
| Memória | **FIFO**, **LRU**, **Optimal** | Estado dos frames a cada referência, hits, faults e taxa |
| Dispositivos | **Matriz de acesso** (R/W/X/U/E), **fila FIFO**, **mutex/semáforo**, modo **exclusivo** | Demonstração com threads reais e simulação determinística |

**Métricas:** tempo de espera (= retorno − burst), retorno (= conclusão − chegada), resposta (= 1ª execução − chegada),
médias, trocas de contexto (CPU passando para outro processo), **índice de justiça de Jain** sobre
`burst/retorno` e detecção de **atraso excessivo/starvation** (espera > 15 ut ou espera/burst ≥ 2).

## 4. Instalação e execução

Requisitos: **Python 3.9+** (testado em 3.12). O simulador e os testes usam só a biblioteca padrão; `matplotlib` é opcional (gráficos PNG).

```bash
git clone <URL-do-repositório> kernellab
cd kernellab
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt                        # opcional (gráficos)
python src/main.py                                     # roda tudo
```

Opções:

| Opção | Efeito |
|---|---|
| `--config ARQ.json` | usa outro conjunto de processos |
| `--quantum N` | altera o quantum do Round Robin |
| `--frames N` | altera a quantidade de frames |
| `--refs 1,2,3,...` | altera a sequência de páginas |
| `--only sched\|memory\|devices` | executa só uma etapa |
| `--no-charts` | não gera PNGs |
| `--save-report docs/resultados.md` | salva a saída em Markdown |

## 5. Formato dos dados de entrada (`data/processes.json`)

```json
{
  "processos": [
    {"pid": "P1", "funcao": "Monitoramento cardíaco", "chegada": 0, "burst": 8,
     "prioridade": 1, "memoria_mb": 120, "dispositivos": ["rede"]}
  ],
  "quantum": 3,
  "memoria": {"frames": 4, "referencias": [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5, 2, 1, 5, 3, 2]}
}
```

Tempos em unidades de tempo (ut) inteiras; burst > 0; PIDs únicos; menor prioridade = mais prioritário.

## 6. Exemplos de uso

```bash
python src/main.py --only sched --quantum 4 --no-charts          # outro quantum
python src/main.py --only memory --frames 3 --refs 7,0,1,2,0,3,0,4,2,3,0,3,2
python src/main.py --only devices                                # matriz, fila e mutex
python src/main.py --save-report docs/resultados.md              # relatório completo + gráficos
```

Uso como biblioteca:

```python
import sys; sys.path.insert(0, "src")
import schedulers as sc, metrics as mt
procs = sc.load_config("data/processes.json")["processes"]
r = sc.round_robin(procs, quantum=3)
print(mt.gantt_text(r)); print(mt.metrics_table(r))
```

## 7. Testes

```bash
python -m unittest discover -s tests -v      # biblioteca padrão
# ou, se tiver pytest:  pytest tests/
```

Cobrem: valores esperados (calculados à mão) de FCFS, SJF, RR e Prioridade; invariantes (retorno = conclusão − chegada,
CPU sem sobreposição, soma dos bursts); CPU ociosa; quantum configurável; entradas inválidas; aging; FIFO/LRU/Optimal
(inclusive a **anomalia de Belady**); matriz de acesso, fila, ausência de sobreposição com mutex, semáforo contador e
acesso exclusivo.

## 8. Resultados principais (cenário MedControl, quantum = 3)

| Algoritmo | Espera média | Retorno médio | Resposta média | Trocas | P4 (alarme) espera | Jain |
|---|---|---|---|---|---|---|
| FCFS | 13,67 | 20,50 | 13,67 | 5 | 18 | 0,674 |
| SJF | 10,67 | 17,50 | 10,67 | 5 | 5 | 0,761 |
| Round Robin (q=3) | 18,00 | 24,83 | **5,33** | 13 | 6 | **0,972** |
| Prioridade (não preemptivo) | 10,67 | 17,50 | 10,67 | 5 | 5 | 0,761 |
| *Prioridade (preemptivo)* | **10,17** | **17,00** | 9,83 | 6 | **0** | 0,799 |
| *Prioridade (preemptivo + aging 5)* | 11,17 | 18,00 | 8,00 | 8 | 0 | 0,777 |

Memória (4 frames, 17 referências): **FIFO** 5 hits / 12 faltas (70,6 %) · **LRU** 7 / 10 (58,8 %) · **Optimal** 10 / 7 (41,2 %).

**Recomendação:** prioridade **preemptiva** com **aging** calibrado (alarme com resposta imediata), LRU (ou aproximação) na
memória, matriz de menor privilégio e mutex/semáforo nos dispositivos. Detalhes em `docs/resultados.md` e no relatório.

![Gantt](docs/img/gantt.png)
![Comparação](docs/img/comparacao_escalonadores.png)

## 9. Limitações e melhorias

- Uma única CPU; bursts conhecidos antecipadamente; sem custo explícito de troca de contexto nem E/S bloqueante.
- Sem inversão de prioridade (seria necessário *priority inheritance*); sem escalonamento de tempo real (EDF/RMS).
- Sequência de páginas fixa, sem modelar tamanho de memória por processo (coluna *Memória* só é informativa).
- Possíveis melhorias: SRTF, múltiplas filas com feedback (MLFQ), algoritmo do relógio/Second Chance, múltiplas CPUs,
  interface web, E/S com bloqueio e retorno à fila de prontos.

## 10. Autor

Carolina Mendes Correia (RA 96043) — Engenharia de Computação — UniFECAF
