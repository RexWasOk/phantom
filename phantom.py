# ─────────────────────────────────────────────────────────────
# phantom.py — Day 3-4
#
# WHAT CHANGED FROM DAY 1-2:
# - Health monitor now running on background thread
# - Watches every replica of every service every 3 seconds
# - Detects death and restarts specific dead replica
# - Other replicas keep running during restart — partial failure
# - Chaos mode supported via --chaos flag
# ─────────────────────────────────────────────────────────────

import yaml
import time
import sys
from core.registry import ServiceRegistry
from core.launcher import launch_service
from core.monitor  import start_monitor

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

    chaos_probability = 0.0
    if "--chaos" in sys.argv:
        index = sys.argv.index("--chaos")

        try:
            chaos_probability = float(sys.argv[index+1])
            print(f"[Phantom] CHAOS MODE — {chaos_probability*100:.0f}% kill probability")
        
        except (IndexError, ValueError):
            print("[Phantom] --chaos requires a number e.g. --chaos 0.2")
            sys.exit(1)
    
    config = load_config()
    services = config["services"]

    registry = ServiceRegistry()
    start_times = {}

    # launch all services and replicas
    for service in services:
        launch_service(service, registry, start_times)
    
    print("\n[Phantom] All replicas launched.")

    # start health monitor on background thread
    start_monitor(services, registry, start_times, chaos_probability)

    print("[Phantom] Health monitor running.")
    print("[Phantom] Press Ctrl+C to stop.\n")

    # print registry state every 5 seconds
    # tomorrow this becomes the rich dashboard

    try:

        while True:

            print("\n[Phantom] Registry state:")
            all_services = registry.get_all_services()

            for name, replicas in all_services.items():
                print(f"  {name}:")
                for r in replicas:
                    print(f"    port={r['port']}  pid={r['pid']}  status={r['status']}")

            time.sleep(5)

    except KeyboardInterrupt:

        shutdown(registry)
        print("[Phantom] Goodbye.")
        sys.exit(0)

if __name__ == "__main__":
    main()



