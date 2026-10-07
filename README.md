# Hydro-Kinematic Logistics Mesh & Digital Twin

A next-generation enterprise logistics architecture designed to maintain continuous supply chain visibility and rerouting capabilities during catastrophic infrastructural failures.

## 🌟 The Problem
During extreme weather events (e.g., unpredicted cloudbursts and flash floods), conventional routing engines fail because they lack physical context, and cellular grid outages sever IoT telemetry.

## 🚀 The Solution
This proof-of-concept leverages **Physics-Informed Neural Networks (PI-GNN)** combined with **Vehicular Delay-Tolerant Networking (VDTN)** to calculate localized fluid dynamics and securely broadcast that intelligence offline between vehicles. It is orchestrated natively using IBM's enterprise ecosystem.

---

## 🏗️ Architecture Stack

### 1. Physics-Informed Graph Neural Network (PI-GNN)
A PyTorch-based routing engine that penalizes predictions violating the **1D Saint-Venant equations** (mass/momentum conservation). It computes a localized **Kinematic Hazard Coefficient** ($y \times V$). If the coefficient exceeds $0.8 \text{ m}^2\text{/s}$, the edge is flagged as a critical failure. The model natively integrates with an **A* Graph Routing algorithm** (`router.py`) to actively calculate safe detours around flooded segments in real-time.

### 2. Vehicular Delay-Tolerant Networking (VDTN)
When cellular infrastructure drops, edge nodes dynamically switch to a "store-carry-and-forward" Wi-Fi Direct protocol. Telemetry is secured using **AES-256 encryption** and authenticated via **ECDSA digital signatures** (`vdtn_crypto.py`).

### 3. Serverless IBM Infrastructure & Agentic Orchestration
*   **IBM Event Streams (Kafka)**: Decouples chaotic, burst-heavy telemetry from the fleet.
*   **IBM Cloud Code Engine**: Provisions serverless containers to run PI-GNN inference dynamically.
*   **IBM BAW (Business Automation Workflow)**: Automates enterprise ERP responses via **watsonx**, including drone dispatching, SMS halt alerts, and inventory reallocation triggers.

### 4. Geospatial Dashboard & PWA Fleet Client
*   **QGIS Dashboard Plugin**: A custom QGIS plugin (`qgis-plugin/plugin_main.py`) running inside QGIS that hooks into the Server-Sent Events (SSE) webhook to update map features, flooded zones, and detours live without reloading.
*   **Driver HUD (PWA Client)**: A fully responsive web app (`driver-hud/`) designed for truck drivers. It consumes the same SSE streams to provide dynamic ETAs, A* detours, simulated Vehicle-to-Vehicle (V2V) proximity radars, and live field reporting.

---

## 📁 Repository Structure & Modules

The repository has been heavily modularized for enterprise scalability:

```text
.
├── pi-gnn/                           # Core PI-GNN Inference & Networking
│   ├── model.py                      # PyTorch PI-GNN Model 
│   ├── router.py                     # A* graph routing engine over NH544
│   ├── webhook_server.py             # Flask Webhook API (/infer, /set_route)
│   ├── sse_server.py                 # Server-Sent Events (SSE) broadcaster
│   ├── mock_event_streams.py         # IBM Event Streams telemetry injection
│   ├── vdtn_node.py                  # VDTN mesh routing protocol
│   ├── vdtn_crypto.py                # AES-256/ECDSA encryption suite
│   └── vdtn_simulation.py            # Simulation runner
├── baw/                              # Business Automation Workflow
│   ├── actions.py                    # Twilio SMS, ERP webhooks
│   ├── config.py                     # BAW Configuration & Secrets
│   ├── mcp_registry.py               # Model Context Protocol registry
│   ├── mcp_tools.py                  # WatsonX MCP tool definitions
│   └── watsonx_config.py             # Orchestrate API configs
├── driver-hud/                       # Progressive Web App (PWA) Client
│   ├── index.html                    # Dashboard UI
│   ├── style.css                     # Responsive Styling
│   ├── app.js                        # SSE consumer & Route ETA logic
│   └── service-worker.js             # Offline caching support
├── qgis-plugin/                      # QGIS Real-Time Extension
│   └── plugin_main.py                # SSE consumer rendering live vectors in QGIS
└── qgis-demo/                        # Static map assets and geometries
    ├── data/                         # GeoJSON graph datasets
    └── hydro_kinematic_demo.qgz      # QGIS Project file
```

---

## 💻 Getting Started

### 1. Run the Backend (PI-GNN Webhook Server)
This server orchestrates the PI-GNN model, the A* router, and broadcasts the SSE streams to all connected clients.
```bash
cd pi-gnn
pip install -r requirements.txt
python3 webhook_server.py
# Runs on http://localhost:8080
```

### 2. Run the Driver HUD (Frontend Client)
Host the frontend locally to simulate the PWA interface used by the fleet:
```bash
python3 -m http.server 4000 --directory driver-hud/
# Open http://localhost:4000 in your browser
```

### 3. Run the QGIS Real-Time Dashboard
1. Open QGIS and load the project: `qgis-demo/hydro_kinematic_demo.qgz`
2. Open the QGIS Python Console (Plugins → Python Console).
3. Open `qgis-plugin/plugin_main.py` in the internal editor and click **Run**.
4. The map will instantly synchronize with the active backend stream.

### 4. Trigger the Autonomous Pipeline
To simulate a cloudburst hitting the NH544 highway and watch the entire architecture react:
```bash
curl -X POST http://localhost:8080/infer \
     -H "Content-Type: application/json" \
     -d '{
           "node_id": "Sensor-NH544-B",
           "metrics": {
             "depth": 1.5,
             "velocity": 2.5,
             "S0": 0.05,
             "n": 0.065
           }
         }'
```
* **Effect**: The PI-GNN model detects a critical hazard > 0.8 m²/s. It fires a background trigger to the IBM BAW webhook, calculates a safe detour using `router.py`, and pushes the new route via SSE to both the QGIS dashboard and the Driver HUD client simultaneously.
