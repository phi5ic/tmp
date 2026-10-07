import json
import queue
import threading

_clients_lock = threading.Lock()
clients: list[queue.Queue] = []

def notify_clients(data: dict):
    msg = f"data: {json.dumps(data)}\n\n"
    with _clients_lock:
        snapshot = list(clients)
    for q in snapshot:
        try:
            q.put_nowait(msg)
        except queue.Full:
            pass

def create_event_stream():
    q: queue.Queue = queue.Queue(maxsize=20)
    with _clients_lock:
        clients.append(q)
    try:
        yield ": connected\n\n"
        while True:
            yield q.get()
    except GeneratorExit:
        with _clients_lock:
            try:
                clients.remove(q)
            except ValueError:
                pass
