import unittest
import subprocess
import time
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.registry import ServiceRegistry
from core.monitor  import is_alive, check_health_url
from core.balancer import RoundRobinBalancer


class TestServiceRegistry(unittest.TestCase):

    def setUp(self):
        """Called before every test — gives each test a fresh registry."""
        self.registry = ServiceRegistry()
        self.registry.register_service("api-server")

    def test_register_service(self):
        """Service should exist after registration."""
        services = self.registry.get_all_services()
        self.assertIn("api-server", services)

    def test_add_replica(self):
        """Replica should appear after being added."""
        proc = subprocess.Popen(
            ["python", "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.registry.add_replica("api-server", 8001, proc.pid, proc)
        replicas = self.registry.get_all_replicas("api-server")
        self.assertEqual(len(replicas), 1)
        self.assertEqual(replicas[0]["port"], 8001)
        proc.terminate()
        proc.wait()

    def test_update_status(self):
        """Status should update correctly."""
        proc = subprocess.Popen(
            ["python", "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.registry.add_replica("api-server", 8001, proc.pid, proc)
        self.registry.update_status("api-server", 8001, "DOWN")
        replicas = self.registry.get_all_replicas("api-server")
        self.assertEqual(replicas[0]["status"], "DOWN")
        proc.terminate()
        proc.wait()

    def test_get_healthy_replicas_filters_correctly(self):
        """Only UP replicas should be returned as healthy."""
        proc1 = subprocess.Popen(
            ["python", "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        proc2 = subprocess.Popen(
            ["python", "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.registry.add_replica("api-server", 8001, proc1.pid, proc1)
        self.registry.add_replica("api-server", 8002, proc2.pid, proc2)
        self.registry.update_status("api-server", 8002, "DOWN")

        healthy = self.registry.get_healthy_replicas("api-server")
        self.assertEqual(len(healthy), 1)
        self.assertEqual(healthy[0]["port"], 8001)

        proc1.terminate(); proc1.wait()
        proc2.terminate(); proc2.wait()

    def test_get_all_replicas_returns_copy(self):
        """Modifying returned list should not affect registry."""
        proc = subprocess.Popen(
            ["python", "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.registry.add_replica("api-server", 8001, proc.pid, proc)
        replicas = self.registry.get_all_replicas("api-server")
        replicas.clear()   # modify the returned list
        # registry should be unaffected
        self.assertEqual(len(self.registry.get_all_replicas("api-server")), 1)
        proc.terminate()
        proc.wait()


class TestIsAlive(unittest.TestCase):

    def test_running_process_is_alive(self):
        proc = subprocess.Popen(
            ["python", "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.assertTrue(is_alive(proc))
        proc.terminate()
        proc.wait()

    def test_finished_process_is_not_alive(self):
        proc = subprocess.Popen(
            ["python", "-c", "print('done')"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        proc.wait()
        time.sleep(0.3)
        self.assertFalse(is_alive(proc))


class TestCheckHealthUrl(unittest.TestCase):

    def test_unreachable_url_returns_false(self):
        result = check_health_url("http://localhost:19999/health", timeout=1)
        self.assertFalse(result)


class TestRoundRobinBalancer(unittest.TestCase):

    def test_cycles_through_replicas(self):
        """Should visit each replica in order and cycle back."""
        balancer = RoundRobinBalancer()
        replicas = [
            {"port": 8001, "status": "UP"},
            {"port": 8002, "status": "UP"},
            {"port": 8003, "status": "UP"},
        ]
        self.assertEqual(balancer.get_next(replicas)["port"], 8001)
        self.assertEqual(balancer.get_next(replicas)["port"], 8002)
        self.assertEqual(balancer.get_next(replicas)["port"], 8003)
        self.assertEqual(balancer.get_next(replicas)["port"], 8001)

    def test_returns_none_when_no_replicas(self):
        """Should return None gracefully when list is empty."""
        balancer = RoundRobinBalancer()
        self.assertIsNone(balancer.get_next([]))

    def test_handles_single_replica(self):
        """Single replica should always be returned."""
        balancer  = RoundRobinBalancer()
        replicas  = [{"port": 8001, "status": "UP"}]
        self.assertEqual(balancer.get_next(replicas)["port"], 8001)
        self.assertEqual(balancer.get_next(replicas)["port"], 8001)


if __name__ == "__main__":
    unittest.main(verbosity=2)