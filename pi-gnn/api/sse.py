import json
import threading
from typing import Iterator

# Global SSE clients lock and list
_clients = []
_clients_lock = threading.RLock()

def register_client():
    """Register a new SSE client queue."""
    import queue
    q = queue.Queue(maxsize=100)
    with _clients_lock:
        _clients.append(q)
    return q

def unregister_client(q):
    """Remove a client queue."""
    with _clients_lock:
        if q in _clients:
            _clients.remove(q)

def broadcast(event_type: str, data: dict):
    """Broadcast an SSE event to all connected clients."""
    with _clients_lock:
        dead_clients = []
        for q in _clients:
            try:
                q.put_nowait({"event": event_type, "data": data})
            except:
                dead_clients.append(q)
        for dq in dead_clients:
            _clients.remove(dq)

def sse_stream(q) -> Iterator[str]:
    """Generator for Flask SSE response."""
    try:
        while True:
            msg = q.get()
            yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
    except GeneratorExit:
        unregister_client(q)
