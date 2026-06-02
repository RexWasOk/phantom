# Phantom

A distributed process orchestration system built in Python from scratch.
Define services in YAML — Phantom spawns multiple replicas of each, monitors their health via HTTP endpoints, automatically restarts failures, and load-balances incoming traffic across healthy replicas only.

Built to understand how Kubernetes and Docker Swarm work under the hood.

---

## Demo

![Phantom Demo](demo.gif)

---

## Features

- **Replica management** — run N copies of each service simultaneously
- **HTTP health checks** — ping each replica's `/health` endpoint every 3 seconds
- **Per-replica restart** — dead replicas restart with exponential backoff while other replicas keep serving traffic uninterrupted
- **Round-robin load balancer** — routes requests across healthy replicas, automatically skips dead ones
- **Live dashboard** — real-time terminal UI showing every replica's status, port, PID, uptime, and restart count
- **Chaos mode** — randomly kill replicas to prove self-healing resilience
- **Graceful shutdown** — Ctrl+C cleanly terminates all managed processes

---

## Demo

Run normally:
```bash
python phantom.py
```

Run with chaos mode:
```bash
python phantom.py --chaos 0.2
```

---

## Architecture

```
config.yaml
     │
     ▼
Phantom Core (phantom.py)
     │
     ├── Launcher (core/launcher.py)
     │       spawns N replicas per service
     │       assigns ports via environment variables
     │
     ├── Service Registry (core/registry.py)
     │       thread-safe single source of truth
     │       tracks every replica — port, PID, status
     │
     ├── Health Monitor Thread (core/monitor.py)
     │       pings /health every 3s per replica
     │       detects failures, triggers per-replica restart
     │       exponential backoff: 2s → 4s → 8s → 16s → 32s
     │
     ├── Load Balancer (core/balancer.py)
     │       one HTTP server per service
     │       round-robin routing across healthy replicas only
     │       returns 503 if all replicas are down
     │
     └── Live Dashboard (rich)
             reads registry every second
             color-coded status per replica
```

---

## Quick Start

```bash
git clone https://github.com/RexWasOk/phantom.git
cd phantom
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
python phantom.py
```

---

## Config

```yaml
services:
  - name: "api-server"
    command: "python services/api.py"
    replicas: 3
    base_port: 8000
    balancer_port: 5001
    health_url: "http://localhost:{port}/health"
```

| Field | Description |
|---|---|
| `replicas` | Number of copies to run simultaneously |
| `base_port` | Starting port — replicas get base+1, base+2, etc. |
| `balancer_port` | Single entry point for all traffic to this service |
| `health_url` | Endpoint Phantom pings every 3s to verify health |

---

## How the Load Balancer Works

Phantom exposes one port per service (e.g. 5001 for api-server). All traffic goes through this single port. Phantom forwards requests to healthy replicas in round-robin order — callers never know which replica handled their request or how many replicas exist.

```
curl http://localhost:5001/hello
→ Response header: X-Served-By: 8001

curl http://localhost:5001/hello
→ Response header: X-Served-By: 8002

curl http://localhost:5001/hello
→ Response header: X-Served-By: 8003
```

Kill a replica — Phantom routes around it instantly. Restart it — Phantom adds it back to rotation automatically.

---

## How Health Monitoring Works

Every 3 seconds, Phantom pings each replica's `/health` HTTP endpoint. A 200 response means healthy. A timeout, connection error, or non-200 response triggers restart.

This is stronger than just checking if a process is running at the OS level — a frozen or broken process can still be "alive" while being completely unable to serve requests. Pinging the health endpoint proves the service is genuinely working.

When a replica fails, Phantom restarts only that replica. Other replicas of the same service keep running and serving traffic — this is partial failure recovery.

---

## Exponential Backoff

When a replica keeps dying, Phantom doesn't hammer it with instant restarts. It waits progressively longer between attempts:

```
Attempt 1 → wait 2s  → restart
Attempt 2 → wait 4s  → restart
Attempt 3 → wait 8s  → restart
Attempt 4 → wait 16s → restart
Attempt 5 → wait 32s → restart
Give up   → mark FAILED
```

This prevents restart storms where a broken service consumes all CPU getting restarted thousands of times per second.

---

## Chaos Mode

Inspired by Netflix's Chaos Monkey. Pass `--chaos 0.2` to give each replica a 20% chance of being randomly killed every monitoring cycle. Proves the system recovers from unexpected failures automatically.

```bash
python phantom.py --chaos 0.3
```

---

## Tech Stack

| Component | Tool |
|---|---|
| Process management | `subprocess.Popen` |
| Concurrency | `threading` |
| Health checks | `requests`, `http.server` |
| Config parsing | `PyYAML` |
| Dashboard | `rich` |
| Load balancing | `http.server` + `itertools.cycle` |
| Port assignment | `os.environ` |

---

## What I Learned Building This

- How Kubernetes manages replica sets and handles pod restarts
- Thread-safe shared state with locks — producer/consumer pattern
- Round-robin load balancing and fault-tolerant traffic routing
- Per-replica failure isolation — partial failure vs complete failure
- Factory pattern for injecting dependencies into HTTP handlers
- Chaos engineering — deliberately injecting failures to prove resilience
- Environment variables for service configuration (same pattern as Docker)

---

## Project Structure

```
phantom/
├── phantom.py          # orchestrator entry point
├── config.yaml         # service definitions
├── core/
│   ├── registry.py     # thread-safe service registry
│   ├── launcher.py     # spawns replicas with port assignment
│   ├── monitor.py      # health monitor + per-replica restart
│   └── balancer.py     # round-robin HTTP load balancer
├── services/
│   ├── api.py          # example service with /health + /hello
│   └── worker.py       # example worker service
├── tests/
│   └── test_phantom.py
└── README.md
```