import datetime
import time
import hashlib

def now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def eta_iso(delay_hours: float) -> str:
    eta = datetime.datetime.utcnow() + datetime.timedelta(hours=delay_hours)
    return eta.strftime("%Y-%m-%dT%H:%M:%SZ")

def generate_incident_id(sensor_node: str) -> str:
    ts = int(time.time())
    tag = hashlib.sha256(f"{sensor_node}:{ts}".encode()).hexdigest()[:8].upper()
    return f"INC-NH544-{tag}"
