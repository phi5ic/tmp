import torch
import torch.nn as nn
import torch.nn.functional as F

DEMO_SEED   = 1
DEMO_EPOCHS = 2000
DEMO_LR     = 0.005

_TRAIN_INPUTS = [
    (torch.tensor([[100.0, 0.01, 0.015, 20.0]]), torch.tensor([[0.2,  0.5]])),   # normal
    (torch.tensor([[100.0, 0.05, 0.065, 20.0]]), torch.tensor([[1.4,  2.2]])),   # flood
]

def seed_and_train(model: "PIGNN") -> None:
    torch.manual_seed(DEMO_SEED)
    model.apply(lambda m: m.reset_parameters() if hasattr(m, 'reset_parameters') else None)

    adj = torch.tensor([[1.0]])
    opt = torch.optim.Adam(model.parameters(), lr=DEMO_LR)
    mse = nn.MSELoss()

    model.train()
    for _ in range(DEMO_EPOCHS):
        opt.zero_grad()
        loss = sum(mse(model(x, adj), y) for x, y in _TRAIN_INPUTS)
        loss.backward()
        opt.step()
    model.eval()

class PIGNN(nn.Module):
    def __init__(self, node_features, hidden_dim, output_features):
        super(PIGNN, self).__init__()
        self.fc1 = nn.Linear(node_features, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, output_features)
        
    def forward(self, x, adj):
        x = F.relu(self.fc1(x))
        x = torch.matmul(adj, x)
        x = self.fc2(x)
        return x

def saint_venant_loss(predictions, inputs, g=9.81):
    y = predictions[:, 0]
    V = predictions[:, 1]
    
    S0 = inputs[:, 1]
    n = inputs[:, 2]
    
    Sf = (n**2 * V**2) / (torch.pow(torch.abs(y) + 1e-6, 4.0/3.0))
    mass_residual = y * V 
    momentum_residual = (V**2 / 2) + g * y - g * (S0 - Sf)
    
    physics_loss = torch.mean(mass_residual**2) + torch.mean(momentum_residual**2)
    return physics_loss

def total_loss(predictions, targets, inputs, lambda_phys=0.1):
    mse_loss = nn.MSELoss()(predictions, targets)
    phys_loss = saint_venant_loss(predictions, inputs)
    return mse_loss + lambda_phys * phys_loss

def calculate_hazard_coefficient(depth, velocity):
    coefficient = depth * velocity
    is_critical_failure = coefficient > 0.8
    return coefficient, is_critical_failure

if __name__ == "__main__":
    from mock_event_streams import IBMEventStreamsMock

    model = PIGNN(node_features=4, hidden_dim=16, output_features=2)
    seed_and_train(model)

    event_stream = IBMEventStreamsMock("chalakudy-basin-telemetry")

    print("\n--- SCENARIO 1: Normal Conditions ---")
    normal_msg = event_stream.produce_telemetry("Sensor-NH544-A", depth=0.2, velocity=0.5, S0=0.01, n=0.015)
    event_stream.consume_and_infer(model, normal_msg)

    print("\n--- SCENARIO 2: Cloudburst (High Slope, High Roughness Debris Flow) ---")
    flood_msg = event_stream.produce_telemetry("Sensor-NH544-B", depth=1.5, velocity=2.5, S0=0.05, n=0.065)
    event_stream.consume_and_infer(model, flood_msg)
