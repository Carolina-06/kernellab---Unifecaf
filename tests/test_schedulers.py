"""Testes dos escalonadores. Valores esperados calculados manualmente (ver docs/)."""
import unittest

from helpers import medcontrol  # noqa: F401  (ajusta sys.path)
import metrics as mt
import schedulers as sc


def gantt_of(res):
    return [(p, s, e) for p, s, e in res.gantt]


class TestMedControl(unittest.TestCase):
    def setUp(self):
        self.p = medcontrol()

    def test_fcfs(self):
        r = sc.fcfs(self.p)
        self.assertEqual(gantt_of(r), [("P1", 0, 8), ("P2", 8, 12), ("P3", 12, 21),
                                       ("P4", 21, 23), ("P5", 23, 35), ("P6", 35, 41)])
        self.assertEqual({k: m.waiting for k, m in r.metrics.items()},
                         {"P1": 0, "P2": 7, "P3": 10, "P4": 18, "P5": 18, "P6": 29})
        a = mt.averages(r)
        self.assertAlmostEqual(a["espera"], 82 / 6)
        self.assertAlmostEqual(a["retorno"], 123 / 6)
        self.assertAlmostEqual(a["resposta"], 82 / 6)
        self.assertEqual(r.context_switches, 5)

    def test_sjf(self):
        r = sc.sjf(self.p)
        self.assertEqual(r.execution_order, ["P1", "P4", "P2", "P6", "P3", "P5"])
        self.assertAlmostEqual(mt.averages(r)["espera"], 64 / 6)
        self.assertAlmostEqual(mt.averages(r)["retorno"], 105 / 6)
        self.assertEqual(r.context_switches, 5)

    def test_round_robin_q3(self):
        r = sc.round_robin(self.p, 3)
        self.assertEqual([x[0] for x in r.gantt],
                         ["P1", "P2", "P3", "P4", "P1", "P5", "P6", "P2", "P3", "P1", "P5", "P6", "P3", "P5"])
        self.assertEqual({k: m.completion for k, m in r.metrics.items()},
                         {"P1": 26, "P2": 21, "P3": 35, "P4": 11, "P5": 41, "P6": 32})
        a = mt.averages(r)
        self.assertAlmostEqual(a["espera"], 108 / 6)
        self.assertAlmostEqual(a["retorno"], 149 / 6)
        self.assertAlmostEqual(a["resposta"], 32 / 6)
        self.assertEqual(r.context_switches, 13)

    def test_priority_non_preemptive(self):
        r = sc.priority(self.p, preemptive=False)
        self.assertEqual(r.execution_order, ["P1", "P4", "P2", "P6", "P3", "P5"])
        self.assertEqual(r.metrics["P4"].waiting, 5)
        self.assertAlmostEqual(mt.averages(r)["espera"], 64 / 6)

    def test_priority_preemptive_alarm_runs_immediately(self):
        r = sc.priority(self.p, preemptive=True)
        self.assertEqual(gantt_of(r), [("P1", 0, 3), ("P4", 3, 5), ("P1", 5, 10), ("P2", 10, 14),
                                       ("P6", 14, 20), ("P3", 20, 29), ("P5", 29, 41)])
        self.assertEqual(r.metrics["P4"].response, 0)
        self.assertEqual(r.metrics["P4"].waiting, 0)
        self.assertAlmostEqual(mt.averages(r)["espera"], 61 / 6)
        self.assertEqual(r.context_switches, 6)

    def test_invariants_all_algorithms(self):
        for r in sc.run_all(self.p, 3):
            for m in r.metrics.values():
                self.assertEqual(m.turnaround, m.completion - m.arrival)
                self.assertEqual(m.waiting, m.turnaround - m.burst)
                self.assertGreaterEqual(m.response, 0)
                self.assertLessEqual(m.response, m.waiting)
            # CPU nunca executa dois processos ao mesmo tempo e não volta no tempo
            for (_, _, e1), (_, s2, _) in zip(r.gantt, r.gantt[1:]):
                self.assertLessEqual(e1, s2)
            # tempo total executado = soma dos bursts
            ran = sum(e - s for pid, s, e in r.gantt if pid)
            self.assertEqual(ran, sum(p.burst for p in self.p))

    def test_fairness_round_robin_is_best(self):
        rs = {r.algorithm: mt.jain_fairness(r) for r in sc.run_all(self.p, 3)}
        self.assertEqual(max(rs, key=rs.get), "Round Robin (q=3)")


class TestEdgeCases(unittest.TestCase):
    def test_cpu_idle_gap(self):
        ps = [sc.Process("A", 0, 2), sc.Process("B", 10, 3)]
        for r in (sc.fcfs(ps), sc.sjf(ps), sc.round_robin(ps, 2), sc.priority(ps, True)):
            self.assertIn((None, 2, 10), r.gantt)
            self.assertEqual(r.context_switches, 1)
            self.assertEqual(r.metrics["B"].waiting, 0)

    def test_quantum_is_configurable(self):
        ps = medcontrol()
        self.assertNotEqual(sc.round_robin(ps, 3).context_switches, sc.round_robin(ps, 100).context_switches)
        # quantum enorme degenera em FCFS
        self.assertEqual(sc.round_robin(ps, 100).execution_order, sc.fcfs(ps).execution_order)

    def test_single_process(self):
        r = sc.round_robin([sc.Process("A", 0, 5)], 2)
        self.assertEqual(r.context_switches, 0)
        self.assertEqual(r.metrics["A"].waiting, 0)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            sc.fcfs([])
        with self.assertRaises(ValueError):
            sc.round_robin([sc.Process("A", 0, 5)], 0)
        with self.assertRaises(ValueError):
            sc.fcfs([sc.Process("A", 0, 0)])
        with self.assertRaises(ValueError):
            sc.fcfs([sc.Process("A", 0, 1), sc.Process("A", 1, 1)])


class TestStarvation(unittest.TestCase):
    def test_aging_reduces_starvation(self):
        ps = sc.stress_scenario()
        plain = sc.priority(ps, preemptive=True)
        aged = sc.priority(ps, preemptive=True, aging_interval=3)
        self.assertGreater(plain.metrics["BKP"].waiting, aged.metrics["BKP"].waiting)
        # sem aging o processo de baixa prioridade só roda depois de todos os de alta
        self.assertEqual(plain.execution_order[-1], "BKP")

    def test_aging_never_overtakes_critical_class(self):
        r = sc.priority(medcontrol(), preemptive=True, aging_interval=2)
        self.assertEqual(r.metrics["P4"].waiting, 0)      # alarme (prio 0) continua imediato

    def test_aging_none_equals_plain_priority(self):
        ps = medcontrol()
        self.assertEqual(sc.priority(ps, True, None).gantt, sc.priority(ps, True).gantt)

    def test_starvation_report_flags_long_waits(self):
        r = sc.fcfs(medcontrol())
        flagged = {d["pid"] for d in mt.starvation_report(r)}
        self.assertIn("P4", flagged)   # alarme esperando 18 ut
        self.assertIn("P6", flagged)


if __name__ == "__main__":
    unittest.main()
