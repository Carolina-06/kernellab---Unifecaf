"""Testes dos algoritmos de substituição de páginas."""
import unittest

from helpers import medcontrol  # noqa: F401
import memory as mem

REFS = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5, 2, 1, 5, 3, 2]
CLASSIC = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]


class TestReplacement(unittest.TestCase):
    def test_enunciado_4_frames(self):
        f, l, o = mem.run_all(REFS, 4)
        self.assertEqual((f.hits, f.faults), (5, 12))
        self.assertEqual((l.hits, l.faults), (7, 10))
        self.assertEqual((o.hits, o.faults), (10, 7))
        self.assertAlmostEqual(f.fault_rate, 12 / 17)

    def test_optimal_is_lower_bound(self):
        for n in range(1, 7):
            f, l, o = mem.run_all(REFS, n)
            self.assertLessEqual(o.faults, l.faults)
            self.assertLessEqual(o.faults, f.faults)

    def test_hits_plus_faults(self):
        for r in mem.run_all(REFS, 4):
            self.assertEqual(r.hits + r.faults, len(REFS))
            self.assertEqual(len(r.steps), len(REFS))

    def test_frame_state_never_exceeds_capacity(self):
        for r in mem.run_all(REFS, 3):
            for s in r.steps:
                self.assertEqual(len(s.frames), 3)
                self.assertIn(s.ref, s.frames)       # página referenciada está na memória

    def test_belady_anomaly_fifo(self):
        """Sequência clássica: FIFO piora ao AUMENTAR frames de 3 para 4."""
        self.assertEqual(mem.fifo(CLASSIC, 3).faults, 9)
        self.assertEqual(mem.fifo(CLASSIC, 4).faults, 10)
        # LRU e Optimal não sofrem a anomalia (algoritmos de pilha)
        self.assertLessEqual(mem.lru(CLASSIC, 4).faults, mem.lru(CLASSIC, 3).faults)
        self.assertLessEqual(mem.optimal(CLASSIC, 4).faults, mem.optimal(CLASSIC, 3).faults)

    def test_enough_frames_only_compulsory_faults(self):
        for r in mem.run_all(REFS, 5):
            self.assertEqual(r.faults, len(set(REFS)))

    def test_lru_step_example(self):
        l = mem.lru(REFS, 4)
        self.assertEqual(l.steps[6].frames, [1, 2, 5, 4])   # ref 5 substitui a página 3
        self.assertEqual(l.steps[6].victim, 3)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            mem.fifo(REFS, 0)

    def test_empty_refs(self):
        self.assertEqual(mem.fifo([], 3).faults, 0)


if __name__ == "__main__":
    unittest.main()
