"""Testes da matriz de acesso, da fila e da exclusão mútua."""
import unittest

from helpers import medcontrol  # noqa: F401
import devices as dv


class TestAccessMatrix(unittest.TestCase):
    def setUp(self):
        self.m = dv.AccessMatrix()

    def test_least_privilege(self):
        self.assertTrue(self.m.allowed("P5", "disco", "E"))
        self.assertTrue(self.m.allowed("P4", "audio", "E"))
        self.assertFalse(self.m.allowed("P1", "disco", "W"))
        self.assertFalse(self.m.allowed("P3", "rede", "U"))
        self.assertFalse(self.m.allowed("P2", "audio", "U"))
        self.assertFalse(self.m.allowed("PX", "disco", "R"))     # processo desconhecido

    def test_only_critical_processes_have_exclusive(self):
        exclusive = {(p, d) for p, devs in self.m.matrix.items() for d, perms in devs.items() if "E" in perms}
        self.assertEqual(exclusive, {("P4", "audio"), ("P4", "rede"), ("P5", "disco")})

    def test_check_raises(self):
        with self.assertRaises(dv.AccessDenied):
            self.m.check("P1", "disco", "W")
        with self.assertRaises(ValueError):
            self.m.check("P1", "rede", "Z")

    def test_all_processes_can_write_log(self):
        for pid in ("P1", "P2", "P3", "P4", "P5", "P6"):
            self.assertTrue(self.m.allowed(pid, "log", "W"))
            self.assertFalse(self.m.allowed(pid, "log", "R"))


class TestQueue(unittest.TestCase):
    def test_fifo_queue_waits(self):
        reqs = [dv.Request("P3", 2, 4), dv.Request("P5", 3, 5), dv.Request("P6", 4, 3)]
        rows, denied = dv.simulate_queue(reqs, "disco")
        self.assertEqual([(r["inicio"], r["fim"], r["espera"]) for r in rows],
                         [(2, 6, 0), (6, 11, 3), (11, 14, 7)])
        self.assertEqual(denied, [])

    def test_unauthorized_request_is_denied(self):
        rows, denied = dv.simulate_queue([dv.Request("P1", 0, 2), dv.Request("P3", 0, 2)], "disco")
        self.assertEqual([r["pid"] for r in rows], ["P3"])
        self.assertEqual(denied[0][0], "P1")

    def test_no_overlap_in_simulated_queue(self):
        reqs = [dv.Request(p, 0, 3) for p in ("P3", "P5", "P6")]
        rows, _ = dv.simulate_queue(reqs, "disco")
        for a, b in zip(rows, rows[1:]):
            self.assertLessEqual(a["fim"], b["inicio"])


class TestConcurrency(unittest.TestCase):
    def test_mutex_prevents_lost_updates(self):
        final, expected = dv.race_condition_demo(True)
        self.assertEqual(final, expected)

    def test_without_mutex_loses_updates(self):
        # Com sleep(0) forçando troca de thread, a perda é praticamente certa.
        final, expected = dv.race_condition_demo(False, n_threads=8, iterations=300)
        self.assertLess(final, expected)

    def test_device_mutex_no_overlap(self):
        dev = dv.threaded_device_demo(("P3", "P5", "P6"), "disco", capacity=1, duration=0.03)
        self.assertEqual(len(dev.log), 3)
        self.assertEqual(dev.overlaps(), 0)

    def test_semaphore_allows_limited_parallelism(self):
        dev = dv.Device("rede", capacity=2)
        import threading
        ts = [threading.Thread(target=dev.use, args=(p, "U", 0.05)) for p in ("P1", "P2", "P6")]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(dev.log), 3)
        # com 2 vagas e 3 pedidos, algum par se sobrepõe, mas nunca 3 ao mesmo tempo
        for pid, _, s, e in dev.log:
            simult = sum(1 for _, _, s2, e2 in dev.log if s2 < e and s < e2)
            self.assertLessEqual(simult, 2)

    def test_exclusive_blocks_everyone(self):
        dev = dv.Device("rede", capacity=2, matrix=dv.AccessMatrix())
        import threading
        ts = [threading.Thread(target=dev.use, args=("P4", "W", 0.05, True)),
              threading.Thread(target=dev.use, args=("P1", "W", 0.05))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(dev.overlaps(), 0)

    def test_exclusive_requires_permission(self):
        dev = dv.Device("rede", capacity=2, matrix=dv.AccessMatrix())
        with self.assertRaises(dv.AccessDenied):
            dev.use("P1", "W", 0.01, exclusive=True)     # P1 não tem 'E' na rede


if __name__ == "__main__":
    unittest.main()
