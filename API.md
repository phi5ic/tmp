# PI-GNN API Endpoints Reference

This document outlines the REST and SSE endpoints provided by the PI-GNN backend microservices.

## 1. Webhook Server (`pi-gnn/webhook_server.py`)
**Base URL**: `http://localhost:8080`

This server handles real-time PI-GNN inference, A* routing, and broadcasts updates to the Driver HUD via Server-Sent Events (SSE).

### `POST /infer`
Triggers the PI-GNN PyTorch model using live sensor metrics. If the hazard coefficient exceeds `0.8`, it automatically recalculates a safe A* route and triggers the IBM BAW workflow.
- **Payload:**
  ```json
  {
    "node_id": "Sensor-NH544-B",
    "metrics": {
      "depth": 1.5,
      "velocity": 2.5,
      "S0": 0.05,
      "n": 0.065
    }
  }
  ```
- **Response:** JSON containing `hazard_coefficient`, `is_critical`, `predicted_depth`, etc.

### `GET /stream`
Server-Sent Events (SSE) endpoint consumed by the Driver HUD.
- **Events Emitted:**
  - `HAZARD_UPDATE`: Real-time severity metrics.
  - `REROUTE_UPDATE`: Emitted when A* generates a new safe path (includes GeoJSON).
  - `STAGE_UPDATE`: Simulation state updates.

### `POST /set_route`
Recalculates the active route for the fleet truck.
- **Payload:** `{"origin": [lat, lon], "destination": [lat, lon]}`
- **Response:** `{"found": true, "length_m": 29390.3}`

### `GET /health`
Simple health check returning `{"status": "ok"}`.

*(Note: The frontend Driver HUD also gracefully attempts calls to `/report`, `/start_sim`, and `/route_coords` to support future V2V mesh network expansions; these gracefully fallback to local offline mode if unimplemented on the server).*

---

## 2. IBM BAW & Watsonx Connector (`baw/watsonx_orchestrate_connector.py`)
**Base URL**: `http://localhost:9090`

This server acts as a Model Context Protocol (MCP) bridge, executing complex business logic like drone dispatch and supply chain realignment when a critical flood is detected.

### `POST /baw/trigger`
Fired automatically by the Webhook Server when `hazard > 0.8`. Executes the full Flood Response Workflow.
- **Headers:** `X-Trigger-Token` (Optional for auth)
- **Payload:** `{"sensor_node": "Sensor-NH544-B", "hazard_coefficient": 3.03, "delay_hours": 4.0}`
- **Response:** JSON summary of actions taken (Drone dispatch, KSDMA alerts, etc.)

### `GET /mcp/tools/list`
Returns the registry of available Watsonx MCP tools.
- **Headers:** `X-Api-Key` (HMAC Auth)
- **Response:** List of tools (e.g. `ksdma_infer`, `drone_dispatch`).

### `POST /mcp/tools/call`
Executes a specific Watsonx MCP tool.
- **Headers:** `X-Api-Key`
- **Payload:** `{"name": "drone_dispatch", "arguments": {"lat": 10.3, "lon": 76.3}}`
- **Response:** Tool execution result.

### `GET /health`
Simple health check returning `{"status": "ok"}`.
