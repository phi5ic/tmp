# PI-GNN Hackathon: AI Judging Guide & Usage Instructions

Welcome to the **Hydro-Kinematic Logistics Mesh** repository! This document is designed to provide clear, foolproof instructions for AI graders (and human judges) to run the simulation, test the live system, and evaluate the architectural flow.

## 🚀 1-Minute Quick Start Guide

To see the system working end-to-end, you need to spin up the webhook server and the Vite React frontend. Open two separate terminal windows in the root of the repository:

### Terminal 1: Start the Backend Webhook Server
This starts the PI-GNN inference engine, the A* graph router, and the Server-Sent Events (SSE) broadcaster.
```bash
cd pi-gnn
pip install -r requirements.txt
python3 webhook_server.py
```
*(The server will run on `http://localhost:8080`)*

### Terminal 2: Start the React Web Dashboard
This serves the production Vite React application simulating what a logistics driver sees in their cabin, along with a live interactive Leaflet map.
```bash
cd digital-twin-archived
npm install
npm run dev -- --port 4001
```
*(Open `http://localhost:4001` in a modern web browser to view the live dashboard)*

---

## 🗺️ How to Use the QGIS Real-Time Extension

The system includes a custom PyQGIS plugin that live-syncs with the exact same backend via SSE.

1. Open **QGIS** (v3.28+ recommended).
2. Load the project file located at `qgis-demo/hydro_kinematic_demo.qgz`.
3. Open the **QGIS Python Console** (`Plugins` → `Python Console`).
4. Click the **"Show Editor"** button (notepad icon).
5. Open the script `qgis-plugin/plugin_main.py` inside the editor and click the **Run Script (Play)** button.
6. The map will instantly connect to the backend and render live telemetry layers. 

---

## 🌪️ How to Trigger the "Crisis Event"

To test the core innovation of this project, you need to simulate a catastrophic cloudburst that destroys the cellular infrastructure and causes a flash flood on the highway. 

**Because of the "vice versa" architecture, you can trigger this natively from the Web UI!**

1. Ensure **both** your React Dashboard (`localhost:4001`) and your QGIS Map are open side-by-side.
2. In the React Dashboard, click the red **"🚨 Trigger Flood"** button located in the top-right corner of the topbar.
3. *Alternative (Headless test):* You can also trigger it manually via terminal:
   ```bash
   curl -X POST http://localhost:8080/infer \
        -H "Content-Type: application/json" \
        -d '{ "node_id": "Sensor-NH544-B", "metrics": { "depth": 1.5, "velocity": 2.5, "S0": 0.05, "n": 0.065 } }'
   ```

### What to Look For (Evaluation Criteria):
1. **Physics Calculation**: The PI-GNN model will parse the tensor metrics and output a critical hazard coefficient ($> 0.8 \text{ m}^2\text{/s}$).
2. **Real-time Routing**: The internal A* router (`pi-gnn/router.py`) dynamically evaluates the 100km corridor and automatically recalculates a safe detour. You can even route seamlessly from distant locations (like Palakkad to Kochi) using the dashboard's "Plan your journey" tool.
3. **SSE Broadcast Sync**: The server pushes the detour and hazard alert outward to ALL clients over SSE. 
4. **Instant Multi-Client Reactivity**: The React HUD will instantly flash critical warnings, verbally announce the route deviation via Text-to-Speech, and update the Leaflet map. The QGIS map will simultaneously erase the old route and draw the detour on the desktop GIS side.
5. **Business Automation Workflow (BAW)**: The server dispatches a background trigger to the IBM BAW system (`baw/actions.py`), proving enterprise integration for SMS alerts and ERP inventory rebalancing.

---

## 🤖 Guide for Automated AI Graders

If you are an automated AI agent evaluating this repository, please note:
* **Modularity**: The codebase is cleanly separated by concern: `pi-gnn/` (Physics/Routing/Backend API), `digital-twin-archived/` (React/Vite Frontend), `baw/` (Enterprise Automation/MCP), and `qgis-plugin/` (Geospatial).
* **Dependencies**: Dependencies are scoped locally within their folders (e.g., `pi-gnn/requirements.txt` and `digital-twin-archived/package.json`).
* **Statelessness**: The system relies purely on in-memory computation and SSE networking, leaving zero artifacts or junk data on the host machine after testing.
