# ─────────────────────────────────────────────────────────────
# 
# FINAL
# 
# ─────────────────────────────────────────────────────────────

import yaml
import time
import sys
from core.registry import ServiceRegistry
from core.launcher import launch_service
from core.monitor  import start_monitor
from core.balancer import start_all_balancers
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich import box
from datetime import datetime

console = Console()

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

def build_dashboard(registry, start_times, restart_counts):

    """
    Builds a fresh table every second showing every replica
    of every service — status, port, PID, uptime, restarts.
    """

    table = Table(
        title="Phantom — Live Dashboard",
        box=box.ROUNDED,
        show_header = True,
        header_style = "bold white"
    )

    table.add_column("Service",  style="cyan",  min_width=18)
    table.add_column("Port",     style="white", min_width=8)
    table.add_column("Status",   min_width=14)
    table.add_column("PID",      style="white", min_width=8)
    table.add_column("Uptime",   style="white", min_width=12)
    table.add_column("Restarts", style="white", min_width=10)

    all_services = registry.get_all_services()
    
    for service_name, replicas in all_services.items():
        for i, replica in enumerate(replicas):

            port = replica["port"]
            status = replica["status"]
            pid    = str(replica["pid"]) if replica["proc"].poll() is None else "—"
            key    = f"{service_name}:{port}"

            # uptime
            if status == "UP" and key in start_times:
                elapsed      = datetime.now() - start_times[key]
                total_secs   = int(elapsed.total_seconds())
                hours        = total_secs // 3600
                minutes      = (total_secs % 3600) // 60
                seconds      = total_secs % 60
                uptime       = f"{hours:02}:{minutes:02}:{seconds:02}"
            
            else:
                uptime = "-"
            
            # restart count
            restarts = str(restart_counts.get(key, 0))

            # color coded status
            if status == "UP":
                status_display = "[green]✓ UP[/green]"
            elif status == "DOWN":
                status_display = "[red]✗ DOWN[/red]"
            elif status == "RESTARTING":
                status_display = "[yellow]↻ RESTARTING[/yellow]"
            elif status == "FAILED":
                status_display = "[bold red]✗ FAILED[/bold red]"
            else:
                status_display = status

            # only show service name on first replica row
            # makes the table easier to read
            display_name = service_name if i == 0 else ""

            table.add_row(
                display_name,
                str(port),
                status_display,
                pid,
                uptime,
                restarts
            )

        # add a blank separator row between services
        table.add_row("", "", "", "", "", "")

    return table


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

    # initialise restart counts
    restart_counts = {}

    # start monitor — pass restart_counts so it can increment
    start_monitor(services, registry, start_times, restart_counts, chaos_probability)

    # start load balancers
    start_all_balancers(services, registry)

    console.print("\n[bold][Phantom] All systems running. Dashboard starting...[/bold]")
    time.sleep(2)

    try:
        with Live(refresh_per_second=1, screen=True) as live:
            while True:
                live.update(build_dashboard(registry, start_times, restart_counts))
                time.sleep(1)

    except KeyboardInterrupt:
        shutdown(registry)
        console.print("[bold green][Phantom] Goodbye.[/bold green]")
        sys.exit(0)

if __name__ == "__main__":
    main()



