import time
import json
import torch
from .model import PIGNN, calculate_hazard_coefficient

class IBMEventStreamsMock:
    def __init__(self, topic):
        self.topic = topic
        print(f"[IBM Event Streams] Connected to topic: {self.topic}")
        
    def produce_telemetry(self, node_id, depth, velocity, S0, n):
        message = {
            "node_id": node_id,
            "timestamp": time.time(),
            "metrics": {"depth": depth, "velocity": velocity, "S0": S0, "n": n}
        }
        print(f"[Producer -> {self.topic}] Published telemetry for {node_id}")
        return json.dumps(message)
        
    def consume_and_infer(self, model, message):
        data = json.loads(message)
        node_id = data["node_id"]
        m = data["metrics"]
        print(f"[Consumer <- {self.topic}] Received data from {node_id}. Triggering PI-GNN inference...")
        
        # Build tensor input: [elevation (mocked), S0, n, width (mocked)]
        x = torch.tensor([[100.0, m["S0"], m["n"], 20.0]], dtype=torch.float32)
        adj = torch.tensor([[1.0]]) # Self loop
        
        predictions = model(x, adj)
        predicted_depth = predictions[0, 0].item()
        predicted_vel = predictions[0, 1].item()
        
        hazard, failure = calculate_hazard_coefficient(predicted_depth, predicted_vel)
        print(f"[Code Engine] Inference complete for {node_id}: Hazard={hazard:.2f} m^2/s. Critical: {failure}")
