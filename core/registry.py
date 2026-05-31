# ─────────────────────────────────────────────────────────────
# core/registry.py
#
# The service registry is the single source of truth in Phantom.
# Every other component reads from or writes to this registry.
#
# Structure:
# {
#   "api-server": [
#       {"port": 8001, "pid": 18423, "status": "UP",   "proc": <Popen>},
#       {"port": 8002, "pid": 18424, "status": "UP",   "proc": <Popen>},
#       {"port": 8003, "pid": 18425, "status": "DOWN", "proc": <Popen>},
#   ],
#   "worker": [
#       {"port": 9001, "pid": 19001, "status": "UP", "proc": <Popen>},
#       {"port": 9002, "pid": 19002, "status": "UP", "proc": <Popen>},
#   ]
# }
# ─────────────────────────────────────────────────────────────

import threading

class ServiceRegistry:

    """
    Thread-safe registry tracking every replica of every service.

    Why a class instead of a plain dict like ProcessPulse?
    Because the registry needs methods — get_healthy(), update_status(),
    register(). Bundling data + methods together is exactly what classes
    are for. The dict lives inside the class, protected by a lock.
    """

    def __init__(self):
        # the actual data store
        self._services = {}

        # one lock protecting the entire registry
        # any thread that wants to read or write must acquire this first
        self._lock = threading.Lock()

    def register_service(self, name):

        """
        Creates an empty entry for a service.
        Called once per service when Phantom starts up.
        """

        with self._lock:
            if name not in self._services:
                self._services[name] = []

    def add_replica(self, name, port, pid, proc):

        """
        Adds a replica to a service's list.
        Called by the launcher after spawning each process.

        Each replica is a dict tracking:
        - port: which port this replica listens on
        - pid:  the OS process ID
        - proc: the Popen object (remote control)
        - status: UP / DOWN / RESTARTING / FAILED
        """

        with self._lock:
            self._services[name].append({
                "port": port,
                "pid": pid,
                "proc": proc,
                "status": "UP"
            })
    
    def update_status(self, name, port, status):

        """
        Updates the status of one specific replica.
        Called by the health monitor when it detects a change.

        We identify replicas by port — every replica has a unique port
        so it's a reliable identifier.
        """

        with self._lock:
            for replica in self._services.get(name, []):
                if replica["port"] == port:
                    replica["status"] = status
                    return
    
    def update_replica(self, name, port, pid, proc):

        """
        After a restart, the replica has a new PID and new proc object.
        This updates the registry to reflect the new process.
        """

        with self._lock:
            for replica in self._services.get(name, []):
                if replica["port"] == port:
                    replica["pid"] = pid
                    replica["proc"] = proc
                    return
    
    def get_all_replicas(self, name):

        """
        Returns a snapshot of all replicas for a service.

        We return a copy — not the actual list.
        Why? Because returning the actual list means the caller
        is holding a reference to our internal data. If the health
        monitor updates the registry while the load balancer is 
        iterating that list — chaos. A copy is always safe.
        """

        with self._lock:
            return list(self._services.get(name, []))
        
    def get_healthy_replicas(self, name):

        """
        Returns only the UP replicas for a service.
        This is what the load balancer calls before routing a request.
        """

        with self._lock:
            return[
                r for r in self._services.get(name, [])
                if["status"] == "UP"
            ]
    
    def get_all_services(self):

        """
        Returns a snapshot of the entire registry.
        Used by the dashboard to display all services and replicas.
        """

        with self._lock:
            # deep copy — so dashboard can iterate safely
            result = {}
            for name, replicas in self._services.items():
                result[name] = list(replicas)
            
            return result
        
    def get_service_names(self):

        with self._lock:
            return list(self._services.keys())


