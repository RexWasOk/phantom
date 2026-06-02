# ─────────────────────────────────────────────────────────────
# core/balancer.py
#
# WHAT THIS DOES:
# Runs an HTTP server on a dedicated port for each service.
# Receives incoming requests and forwards them to healthy
# replicas using round-robin routing.
#
# HOW IT WORKS:
# 1. Request arrives at load balancer port (e.g. 5001)
# 2. Balancer asks registry "give me healthy replicas of api-server"
# 3. Balancer picks the next replica in round-robin order
# 4. Balancer forwards the request to that replica's port
# 5. Balancer sends the replica's response back to the caller
#
# THE CALLER NEVER KNOWS WHICH REPLICA HANDLED THEIR REQUEST.
# THAT'S THE ENTIRE POINT.
# ─────────────────────────────────────────────────────────────

import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from itertools import cycle

class RoundRobinBalancer:

    """
    Tracks which replica to send the next request to.

    itertools.cycle turns a list into an infinite loop:
    cycle([8001, 8002, 8003]) → 8001, 8002, 8003, 8001, 8002, 8003, ...

    But healthy replicas change over time — a replica dies, gets
    restarted, new ones added. So we can't just cycle a fixed list.
    We rebuild the cycle every time we need the next replica,
    based on what's currently healthy in the registry.

    The _index tracks our position so we don't always start from
    the same replica after rebuilding.
    """

    def __init__(self):
        self.index = 0
        self._lock = threading.Lock()

    def get_next(self, healthy_replicas):

        """
        Returns the next healthy replica in round-robin order.
        Returns None if no healthy replicas exist.
        """

        if not healthy_replicas:
            return None
        
        with self._lock:
            # wrap index around if it exceeds current replica count (make it a cycle)
            # this handles the case where replicas are removed

            self._index = self._index % len(healthy_replicas)
            replica = healthy_replicas[self._index]
            self._index = (self._index+1) % len(healthy_replicas)

        return replica


class LoadBalancerHandler(BaseHTTPRequestHandler):

    """
    HTTP handler for the load balancer.

    When a request comes in:
    1. Get healthy replicas from registry
    2. Pick next one via round-robin
    3. Forward request to that replica
    4. Send response back to caller

    self.service_name and self.registry are injected by the factory
    function below — because BaseHTTPRequestHandler doesn't allow
    passing custom constructor arguments easily.
    """

    def do_GET(self):
        self._handle_request("GET")
    
    def do_POST(self):
        self._handle_request("POST")

    def _handle_request(self, method):

        # get healthy replicas from registry
        healthy = self.registry.get_healthy_replicas(self.service_name)

        if not healthy:

            # no healthy replicas — return 503 Service Unavailable
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"No healthy replicas available")
            print(f"[Balancer] {self.service_name}: no healthy replicas!")
            return
        
        # pick next replica via round-robin
        replica = self.balancer.get_next(healthy)
        port = replica["port"]

        # forward the request to the chosen replica
        target_url = f"http://localhost:{port}{self.path}"

        # For GET — simple. Just call requests.get() on the replica's URL. No body to worry about.

        """
        For POST — the caller sent some data in the request body. We need to:

        Read how many bytes the body contains from Content-Length header
        Read exactly that many bytes from self.rfile (the incoming request stream)
        Forward those bytes to the replica
        """
        
        try:

            if method == "GET":
                response = requests.get(target_url, timeout=5) 
            
            else:           
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                response = requests.post(target_url, data=body, timeout=5)
            
            # send replica's response back to the original caller
            self.send_response(response.status_code)
            self.send_header("Content-Type",
                             response.headers.get("Content-Type", "application/json"))
            
            # tell caller which replica actually handled the request
            # useful for debugging and demos

            self.send_header("X-Served-By", str(port))  # custom header we add, tells caller which replica handled it
            self.end_headers()
            self.wfile.write(response.content)

            print(f"[Balancer] {self.service_name}: "
                  f"{method} {self.path} → port {port} "
                  f"({response.status_code})")
            
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"Replica error: {str(e)}".encode())

        """
        502 means Bad Gateway — "I tried to forward your request but the upstream server failed."
        This handles the rare case where a replica dies at the exact moment we're forwarding to it —
        between the health check and the actual request. The balancer doesn't crash — it catches
        the error and tells the caller professionally.
        """
    
    def log_message(self, format, *args):
        pass      # suppress default logs — we have our own above

def make_handler(service_name, registry, balancer):

    """
    Factory function — creates a handler class with registry
    and balancer injected into it.

    Why a factory? BaseHTTPRequestHandler creates handler instances
    itself — we can't pass arguments to __init__ directly.
    The factory creates a NEW CLASS with our objects baked in
    as class attributes. Every instance of that class then has
    access to them via self.

    This is called the factory pattern.

    IN DETAIL-

    You want your handler to use two objects:
    -> registry — to get healthy replicas
    -> balancer — for round-robin logic

    Because inside the handle request func in the above class, we wrote-
    healthy = self.registry.get_healthy_replicas(self.service_name)
    replica = self.balancer.get_next(healthy)

    So self.registry and self.balancer need to exist somehow on the handler object.

    Why you can't just pass them normally??
    Normally when you create an object you pass things through __init__:
    class LoadBalanceHandler:
    def __init__(self, registry, balancer):
        self.registry = registry
        self.balancer = balancer
    
    Why didnt we do it like this?
    Its because we never call the handler by ourselves.

    Python's HTTPServer creates handler instances automatically every time a request arrives.
    You have no control over how it creates them. It always calls the handler like this internally:
    handler = HandlerClass(request, client_address, server)

    Three fixed arguments(request, client_address, server). Always. 
    You can't add registry and balancer as extra arguments — HTTPServer doesn't know about them and won't pass them.
    
    So you're stuck. You need registry and balancer inside the handler, but you can't pass them through __init__.

    !! The solution — bake them into the class itself !!
    Instead of passing data to an instance, you attach data directly to the class.

    LoadBalancerHandler.registry = registry
    LoadBalancerHandler.balancer = balancer

    Now when any instance of LoadBalancerHandler accesses self.registry — 
    Python first checks the instance, doesn't find it, then checks the class, finds it there.

    The factory creates a brand new class each time for each service.
    """

    class Handler(LoadBalancerHandler):   # This creates a brand new class that inherits everything from LoadBalancerHandler.
        pass           # pass means the new class adds nothing new — it's an exact copy of LoadBalancerHandler but as a completely separate class object in memory.

    Handler.service_name = service_name 
    Handler.registry     = registry
    Handler.balancer     = balancer

    # Now the data is attached to THIS specific new class — not the parent LoadBalancerHandler.
    # So each service gets its own private class with its own private data.

    """
    # first call to make_handler
    Handler_1 = a new class, inherits LoadBalancerHandler

    # second call to make_handler  
    Handler_2 = another new class, also inherits LoadBalancerHandler

    # Handler_1 and Handler_2 are completely separate classes
    # modifying one doesn't affect the other
    """

    return Handler

def start_balancer_for_service(service, registry):

    """
    Starts a load balancer for one service on its balancer_port.

    Each service gets its own load balancer on its own port.
    config.yaml specifies balancer_port for each service.
    """

    name = service["name"]
    balancer_port = service.get("balancer_port")

    if not balancer_port:
        print(f"[Balancer] No balancer_port for {name} — skipping")
        return None
    
    balancer = RoundRobinBalancer()
    handler = make_handler(name, registry, balancer)
    server = HTTPServer(("localhost", balancer_port), handler)

    thread = threading.Thread(
        target = server.serve_forever,
        daemon=True
    )
    thread.start()

    print(f"[Balancer] {name} load balancer on port {balancer_port}")
    return server

def start_all_balancers(services, registry):

    balancers = []
    for service in services:

        server = start_balancer_for_service(service, registry)
        if server:
            balancers.append(server)
    
    return balancers



    

    

