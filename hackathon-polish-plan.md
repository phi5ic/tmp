# Hackathon Polish Plan — Hydro-Kinematic Logistics Mesh

## Overview

The project is functionally strong (PI-GNN physics, VDTN mesh, deck.gl twin, BAW workflow all work) but has seven concrete gaps that will hurt a judging panel's confidence: broken SSE when deployed, wrong segment mapping in the live binding, missing frontend error resilience, an unauthenticated BAW trigger endpoint, no CORS/proxy config for the dev server, a dead CSS class for the leaflet map that no longer exists, and the mcp.json declares a drone-dispatch tool that is never implemented. This plan fixes all seven, ordered by impact.

---

## Sub-Task 1 — Fix the SSE backend URL and add onerror resilience

**Status:** `[ ] pending`

**Intent:**
`App.jsx` hard-codes `http://localhost:8000/stream` as the SSE endpoint. When the digital twin is served via Vite's dev server (port 5173) and the backend is on a different port, `EventSource` fires an immediate CORS error and the `try/catch` around it is useless — `new EventSource(url)` never throws; it only fires `onerror`. The twin therefore renders with zero live data even locally. Fix both the configurable URL and the missing error handler.

**Expected Outcomes:**
- SSE URL is driven by `VITE_BACKEND_URL` env var, defaulting to empty string so Vite's proxy handles it
- `eventSource.onerror` logs to the on-screen console panel instead of silently failing
- SSE reconnection state is visible to judges in the log panel

**Todo List:**
1. In `digital-twin/src/App.jsx`, replace the hard-coded `"http://localhost:8000/stream"` with `${import.meta.env.VITE_BACKEND_URL || ''}/stream`
2. Add an `eventSource.onerror` handler that calls `addLog("SSE: Connection to telemetry server lost — retrying...", "alert")`
3. Create `digital-twin/.env.example` documenting `VITE_BACKEND_URL=http://localhost:8080`
4. Add `VITE_BACKEND_URL` to the README deployment section

**Relevant Context:**
- `digital-twin/src/App.jsx` lines 48–63 — the SSE `useEffect`
- Vite uses `import.meta.env.VITE_*` (not `process.env.REACT_APP_*`)
- The backend (webhook_server.py) runs on PORT 8080 (Code Engine default)

---

## Sub-Task 2 — Fix the Vite dev proxy (CORS)

**Status:** `[ ] pending`

**Intent:**
The Vite dev server runs on port 5173; the Flask backend on 8080. The browser blocks cross-origin `EventSource` and `fetch` calls unless the backend sends CORS headers (it does not). Adding a Vite proxy rule routes `/stream` and `/infer` through the same origin, eliminating CORS entirely in development without touching the Flask app.

**Expected Outcomes:**
- `npm run dev` + backend running locally produces a fully working SSE binding with no CORS console errors
- Proxy is transparent — `App.jsx` uses relative URLs (`/stream`) via `VITE_BACKEND_URL=''`

**Todo List:**
1. Edit `digital-twin/vite.config.js` to add a `server.proxy` block routing `/stream`, `/infer`, and `/health` to `http://localhost:8080`

**Relevant Context:**
- `digital-twin/vite.config.js` lines 1–7 — currently has no proxy config
- Sub-Task 1 must complete first (relative URLs needed before proxy is useful)

---

## Sub-Task 3 — Fix the SSE segment ID mapping in webhook_server

**Status:** `[ ] pending`

**Intent:**
`webhook_server.py` line 165 hard-codes `affected_segment_ids: [f"ORIG-SEG-{i}" for i in range(150, 300)]` regardless of which sensor node fired. The actual `routes.geojson` has segments `ORIG-SEG-0` through `ORIG-SEG-N` (N ≈ 600). The range 150–300 is arbitrary and covers only a mid-section of the route. A judge watching the live demo will see only a partial segment light up and will immediately notice the mismatch.

Replace the hard-coded range with a sensor-node-to-segment lookup table that maps the two demo sensor nodes (`Sensor-NH544-A`, `Sensor-NH544-B`) to meaningful segments — B covers the flood zone (mid-route ~segments 100–400), A covers the early approach.

**Expected Outcomes:**
- Each sensor node lights up the correct geographic stretch of the route on the digital twin canvas
- The SSE payload `affected_segment_ids` is clearly derived from sensor identity, not an arbitrary slice

**Todo List:**
1. Add a `SENSOR_SEGMENT_MAP` dict in `webhook_server.py` above `notify_clients` mapping node IDs to `(start, end)` index ranges derived from the actual GeoJSON segment count
2. Replace the `range(150, 300)` expression in `notify_clients` call with a lookup against `SENSOR_SEGMENT_MAP`, defaulting to `range(0, 600)` (entire route) for unknown nodes
3. Add `severity_class` field to the SSE payload so the frontend log can display `SAFE / WARNING / CRITICAL` text

**Relevant Context:**
- `pi-gnn/webhook_server.py` lines 160–165 — the `notify_clients` call
- `digital-twin/public/routes.geojson` — segments are `ORIG-SEG-0` through `ORIG-SEG-{N}`; check exact count
- `baw/mcp.json` confirms `Sensor-NH544-B` is the flood-zone node

---

## Sub-Task 4 — Secure the BAW trigger endpoint

**Status:** `[ ] pending`

**Intent:**
`/baw/trigger` in `watsonx_orchestrate_connector.py` is a POST endpoint that autonomously dispatches SMS to drivers, POSTs to warehouse webhooks, and calls the ERP API. It currently has zero authentication. Any HTTP client that can reach the container can trigger it. For a hackathon demo this is a red flag — judges assessing the IBM Cloud Code Engine deployment will ask about it. The fix is a simple shared-secret token check controlled by a `BAW_TRIGGER_TOKEN` env var.

**Expected Outcomes:**
- Requests to `/baw/trigger` without the correct `X-Trigger-Token` header receive a `401` response
- `webhook_server.py` `_trigger_baw_async` sends the token in the header
- When `BAW_TRIGGER_TOKEN` is empty (local dev / demo mode), the check is bypassed cleanly

**Todo List:**
1. In `baw/watsonx_orchestrate_connector.py`, add `BAW_TRIGGER_TOKEN = os.environ.get("BAW_TRIGGER_TOKEN", "")` near the other config constants
2. At the top of the `baw_trigger()` route handler, add: if token is set and header does not match, `abort(401)`
3. In `pi-gnn/webhook_server.py`, pass `X-Trigger-Token` header in `_trigger_baw_async`'s `requests.post` call using the same env var
4. Add `BAW_TRIGGER_TOKEN` to the `ibmcloud ce secret create` command in `README.md`

**Relevant Context:**
- `baw/watsonx_orchestrate_connector.py` lines 282–325 — the `/baw/trigger` route
- `pi-gnn/webhook_server.py` lines 160–176 — `_trigger_baw_async`
- The `_require_api_key()` helper already in the connector (lines 53–58) is the pattern to follow

---

## Sub-Task 5 — Add missing `requests` to pi-gnn requirements and clean up stale CSS

**Status:** `[ ] pending`

**Intent:**
Two small but ship-blocking issues:
1. `pi-gnn/requirements.txt` is missing `requests>=2.31.0`. `webhook_server.py` imports `requests` (line 30) to call the BAW endpoint. A `docker build` of the pi-gnn image will succeed (because `pip install` on the builder stage won't error), but the container will crash at import time with `ModuleNotFoundError`.
2. `digital-twin/src/index.css` contains `.leaflet-container`, `.truck-marker`, `.fleeing-marker`, `.vdtn-ping`, `.glowing-heatmap`, and `.rain-drop` — all Leaflet-era classes. The app now uses deck.gl; none of these are rendered. Dead CSS doesn't break anything but signals unfinished migration to judges reviewing source code.

**Expected Outcomes:**
- `docker build` of `pi-gnn/` completes and container starts without import errors
- `index.css` contains only classes that are actually applied in the current `App.jsx`

**Todo List:**
1. Add `requests>=2.31.0` to `pi-gnn/requirements.txt`
2. In `digital-twin/src/index.css`, remove the blocks for `.leaflet-container`, `.truck-marker`, `.truck-marker.offline`, `.fleeing-marker`, `.vdtn-ping`, `.rain-overlay`, `.rain-drop`, `.glowing-heatmap` (lines 36–302, keeping everything above line 36 and from `.container-status` onward)

**Relevant Context:**
- `pi-gnn/requirements.txt` — currently `torch`, `flask`, `gunicorn` only
- `digital-twin/src/index.css` lines 36–302 — the stale Leaflet/animation CSS
- `digital-twin/src/App.jsx` — verify none of those class names appear before deleting

---

## Sub-Task 6 — Implement the drone dispatch MCP tool

**Status:** `[ ] pending`

**Intent:**
`.bob/mcp.json` declares `"trigger": "cellular_dead_zone_entered"` → `"alertType": "autonomous_drone_dispatch"` (lines 29–37). This is one of the most visually striking features in the architecture diagram (judges will read the MCP config). But `watsonx_orchestrate_connector.py` has no corresponding tool. The fix is a `drone_dispatch` MCP tool that, when called, logs the dispatch command and posts it to the BAW callback URL — matching the demo scenario where `Fleeing-Vehicle-02` enters the dead zone.

**Expected Outcomes:**
- `GET /mcp/tools/list` returns a `drone_dispatch` tool alongside the three existing tools
- `POST /mcp/tools/call` with `"name": "drone_dispatch"` executes and returns a structured dispatch confirmation
- The tool is wired into `App.jsx` SSE handler so it fires a log entry when stage 3 (cellular outage) is reached
- `.bob/mcp.json` `mcpServers.tools` array is updated to include `drone_dispatch`

**Todo List:**
1. Add `drone_dispatch` entry to `MCP_TOOL_REGISTRY` in `watsonx_orchestrate_connector.py` with `inputSchema` requiring `node_id`, `sector`, `priority`
2. Add `_tool_drone_dispatch(args)` implementation that builds a dispatch payload and either POSTs to `BAW_CALLBACK_URL` or logs in demo mode
3. Add `"name": "drone_dispatch"` branch to the `tools_call` dispatch switch in `watsonx_orchestrate_connector.py`
4. Add `drone_dispatch` to the `mcpServers.hydro-kinematic-orchestrate.tools` array in `.bob/mcp.json`
5. In `App.jsx`, when `stage === 3`, `addLog("MCP: drone_dispatch triggered for NH544_Sector7_Corridor", "info")`

**Relevant Context:**
- `baw/watsonx_orchestrate_connector.py` lines 65–124 — `MCP_TOOL_REGISTRY` and tool implementations
- `.bob/mcp.json` lines 29–37 — drone dispatch action, and lines 72–87 — `mcpServers.tools` array
- `digital-twin/src/App.jsx` lines 109–113 — Stage 3 log entries

---

## Sub-Task 7 — Add a live hazard metric card and SSE live indicator to the UI

**Status:** `[ ] pending`

**Intent:**
The metrics panel currently shows `flowDepth`, `flowVel`, `manningN`, and `hazardCoef` — all driven by the scripted animation, not the live SSE feed. When the backend is connected, `liveHazard` state is set but never displayed anywhere in the UI. A judge running the live demo will not see any difference between SSE-connected and scripted mode. Adding one small visual indicator — a "LIVE" badge next to the hazard card that turns green when SSE data arrives, and updating the hazard card value from `liveHazard` when available — closes this gap.

**Expected Outcomes:**
- When `liveHazard !== null`, the hazard metric card displays the live value instead of the scripted `hazardCoef`
- A small `LIVE` / `SIM` badge in the header panel indicates whether the SSE connection is active
- The log panel receives an entry `"[SSE CONNECTED] Live PI-GNN telemetry feed active"` when the first `HAZARD_UPDATE` message arrives
- `index.css` gets the `.live-badge` style for the indicator

**Todo List:**
1. Add `sseConnected` boolean state to `App.jsx`, set to `true` on first successful `onmessage` event
2. In the metrics panel hazard card, display `liveHazard ?? hazardCoef` as the value; add `(LIVE)` suffix when `sseConnected` is true
3. Add a small `LIVE` / `SIM` badge in the header panel next to the Code Engine status badge, coloured green when `sseConnected`
4. Call `addLog("[SSE CONNECTED] Live PI-GNN telemetry feed active", "success")` on first connection
5. Add `.live-badge` CSS class to `index.css`

**Relevant Context:**
- `digital-twin/src/App.jsx` lines 36–38 — `hazardSegments` and `liveHazard` state (sseConnected is missing)
- `digital-twin/src/App.jsx` lines 258–268 — header panel where badge goes
- `digital-twin/src/App.jsx` lines 285–289 — hazard metric card
- `digital-twin/src/index.css` lines 304–322 — `.container-status` pattern to follow for the badge style
