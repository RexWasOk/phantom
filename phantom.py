# ─────────────────────────────────────────────────────────────
# phantom.py — Day 1
#
# WHAT THIS VERSION DOES:
# - Reads config.yaml
# - Launches N replicas per service
# - Registers them all in ServiceRegistry
# - Prints registry state so we can verify it works
#
# WHAT'S MISSING (coming next days):
# - Health monitor
# - Load balancer
# - Dashboard
# ─────────────────────────────────────────────────────────────

import yaml
import time
import sys
from core.registry import ServiceRegistry
from core.launcher import launch_service

def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)
    
def shutdown(registry):
    print("\n[Phantom] Shutting down all replicas...")
    all_services = registry.get_all_services()

    for name, replicas in all_services.items():
        for replica in replicas:
            proc = replica["proc"]
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
                print(f"[Phantom] Stopped {name} replica on port {replica['port']}")

def main():

    config = load_config()
    services = config["services"]

    registry = ServiceRegistry()
    start_times = {}

    # launch all services and their replicas
    for service in services:
        launch_service(service, registry, start_times)
    
    print("\n[Phantom] All replicas launched.")
    print("[Phantom] Registry state:\n")

    # print registry so we can verify everything launched correctly
    all_services = registry.get_all_services()

    for name, replicas in all_services.items():
        print(f"  {name}:")
        for r in replicas:
            print(f"    port={r['port']}  pid={r['pid']}  status={r['status']}")
    
    print("\n[Phantom] Press Ctrl+C to stop.\n")

    try:

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        shutdown(registry)
        print("[Phantom] Goodbye.")
        sys.exit(0)

if __name__ == "__main__":
    main()


