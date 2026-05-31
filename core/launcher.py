# ─────────────────────────────────────────────────────────────
# core/launcher.py
#
# Responsible for ONE thing — spawning processes.
# Takes a service config, spawns N replicas, registers them.
#
# Key difference from ProcessPulse:
# ProcessPulse launched one process per task.
# Phantom launches N replicas per service, each on its own port.
# ─────────────────────────────────────────────────────────────

import subprocess
from datetime import datetime

def get_port(base_port, replica_index):

    """
    Calculates the port for a replica.

    base_port=8000, replica_index=0 → port 8001
    base_port=8000, replica_index=1 → port 8002
    base_port=8000, replica_index=2 → port 8003

    We start from base_port+1 so base_port itself stays free.
    We could use it for the load balancer later.
    """

    return base_port + replica_index + 1

def launch_replica(service, port):

    """
    Launches one replica of a service on a specific port.

    We pass the port as an environment variable — PORT=8001.
    The service script reads this variable to know which port
    to start its HTTP server on.

    Why environment variables instead of command line args?
    Cleaner separation. The command stays simple:
        "python services/api.py"
    Port assignment is handled by the launcher, not the service.

    Every running process on your computer has a set of key-value 
    pairs attached to it called environment variables. They're like a private notepad the OS gives every process.

    os.environ() -> its a dict of ALL environment variables
    os.environ["PATH"] -> reads path variable
    os.environ.get("PORT", 8001) -> reads PORT, returns 8001 if not set

    """

    import os

    # copy current environment and add PORT variable

    env = os.environ.copy() # takes a snapshot of all current environment variables
    env["PORT"] = str(port) # adds one new variable to that snapshot

    proc = subprocess.Popen(
        service["command"].split(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env                  
    )

    # launches the service process with this modified environment
    # The service inherits everything PLUS the PORT variable

    return proc

def launch_service(service, registry, start_times):

    """
    Launches all replicas for one service and registers them.

    For a service with replicas=3 and base_port=8000:
    - launches replica on port 8001
    - launches replica on port 8002
    - launches replica on port 8003
    - registers all three in the registry
    """

    name = service["name"]
    replicas = service.get("replicas", 1)
    base_port = service.get("base_port", 8000)

    registry.register_service(name)

    for i in range(replicas):
        port = get_port(base_port, i)
        proc = launch_replica(service, port)

        registry.add_replica(
            name = name,
            port = port,
            pid = proc.pid,
            proc = proc
        )

        # record start time for uptime tracking
        start_times[f"{name}:{port}"] = datetime.now()

        print(f"[Phantom] Launched {name} replica on port {port} (PID {proc.pid})")

