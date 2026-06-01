# ─────────────────────────────────────────────────────────────
# core/monitor.py
#
# WHAT THIS DOES:
# Runs on a background thread. Every 3 seconds it pings every
# replica of every service via their /health endpoint.
# If a replica fails — marks it DOWN and restarts it.
#
# HOW IT'S DIFFERENT FROM PROCESSPULSE:
# ProcessPulse watched one process per task.
# Phantom watches N replicas per service. When replica 2 of
# api-server dies — only that replica restarts. Replicas 1 and 3
# keep serving traffic uninterrupted.
#
# KEY CONCEPT — PARTIAL FAILURE:
# In ProcessPulse, if worker_a died — that service was completely
# down until restart. In Phantom, if one replica dies — the other
# replicas absorb the traffic. True fault tolerance.
# ─────────────────────────────────────────────────────────────

import time
import threading
import requests
import subprocess
import random
from datetime import datetime

def is_alive(proc):
    return proc.poll() is None

def check_health_url(url, timeout=3):

    """
    Pings the worker's /health endpoint.
    Returns True if we get a 200 response — genuinely healthy.
    Returns False if connection refused, timeout, or any error.

    timeout=3 means if the worker doesn't respond within 3 seconds
    we consider it unhealthy. A healthy service responds instantly.
    We don't want Pulse hanging forever waiting for a dead service.
    """
     
    try: 
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    
    except requests.exceptions.ConnectionError:
        return False

    except requests.exceptions.Timeout:
        return False

    except Exception:
        return False

def restart_replica(service, replica, registry, start_times):

    """
    Restarts ONE specific replica with exponential backoff.

    Key difference from ProcessPulse:
    ProcessPulse restarted the entire service.
    Phantom restarts only the dead replica — identified by its port.
    Other replicas of the same service keep running untouched.

    After restart, we update the registry with the new PID and proc
    object — the port stays the same, only the process changes.
    """

    import os

    name = service["name"]
    port = replica["port"]
    wait_time = 2
    max_retries = 5

    print(f"[Monitor] Restarting {name} replica on port {port}...")

    for attempt in range(1, max_retries+1):

        registry.update_status(name, port, "RESTARTING")
        time.sleep(wait_time)

        # launch a fresh process on the same port
        env = os.environ.copy()
        env["PORT"] = str(port)

        new_proc = subprocess.Popen(
            service["command"].split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )

        # give it 2 seconds to start up
        time.sleep(2)

        if is_alive(new_proc):
            # update registry with new process info
            registry.update_replica(name, port, new_proc.pid, new_proc)
            registry.update_status(name, port, "UP")

            # update start time for uptime tracking
            start_times[f"{name}:{port}"] = datetime.now()

            print(f"[Monitor] ✓ {name}:{port} restarted successfully (PID {new_proc.pid})")

            return True
        
        else:
            print(f"[Monitor] ✗ {name}:{port} died again (attempt {attempt}/{max_retries})")
            registry.update_status(name, port, "DOWN")
            wait_time *= 2

    
    print(f"[Monitor] ✗ {name}:{port} permanently failed after {max_retries} attempts")
    registry.update_status(name, port, "FAILED")
    return False

def monitor_loop(services, registry, start_times, chaos_probability=0.0):

    """
    The main monitoring loop — runs forever on a background thread.

    For each service → for each replica → check health.
    If unhealthy → restart that specific replica.

    chaos_probability works exactly like ProcessPulse —
    randomly kills replicas to test self-healing.
    """

    # give all replicas time to start their health servers
    time.sleep(3)
    print("[Monitor] Health monitor started.\n")

    # track which replicas have permanently failed
    # so we don't keep trying to restart them

    permanently_failed = set()   # stores "service_name:port" strings

    while True:
        
        for service in services:
            name = service["name"]
            health_url_template = service.get("health_url", "")

            # get a snapshot of all replicas for this service
            replicas = registry.get_all_replicas(name)

            for replica in replicas:
                port = replica["port"]
                proc = replica["proc"]
                key = f"{name}:{port}"    # unique identifier for this replica

                if key in permanently_failed:
                    continue

                # ── CHAOS MODE ──
                if chaos_probability>0.0 and is_alive(proc):
                    if random.random() < chaos_probability:
                        print(f"[Chaos] Killing {name} replica on port {port}")
                        proc.terminate()
                
                # ── HEALTH CHECK ──
                # first check OS level

                if not is_alive(proc):
                    registry.update_status(name, port, "DOWN")
                    success = restart_replica(service, replica, registry, start_times)
                    if not success:
                        permanently_failed.add(key)
                    continue

                # then check HTTP health endpoint
                
                if health_url_template:
                    health_url = health_url_template.replace("{port}", str(port))
                    healthy = check_health_url(health_url)
                
                else:
                    healthy = True

                if healthy:
                    registry.update_status(name, port, "UP")
                
                else:
                    registry.update_status(name, port, "DOWN")
                    success = restart_replica(service, replica, registry, start_times)
                    if not success:
                        permanently_failed.add(key)
        
        time.sleep(3)
    
def start_monitor(services, registry, start_times, chaos_probability=0.0):

    """
    Starts the monitor loop on a background daemon thread.
    Called once from phantom.py main().
    """

    thread = threading.Thread(
        target = monitor_loop,
        args = (services, registry, start_times, chaos_probability),
        daemon = True
    )

    thread.start()
    return thread

