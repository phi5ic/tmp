# Hackathon Polish Plan 2 — Second-Pass Improvements

## Overview

The first polish pass fixed all structural bugs and wiring gaps. This second pass targets judge-facing polish: professional Git hygiene, production CORS configuration, a self-restarting demo loop, interactive 3D segment tooltips, a visible reroute path on the WebGL canvas, deterministic PI-GNN demo outputs, a lazy-import fix, and a Mermaid architecture diagram in the README. All items were identified by reading actual file contents — nothing speculative.

---

## Sub-Task A — Add root `.gitignore`

**Status:** `[ ] pending`

**Intent:**
No `.gitignore` exists at the workspace root. IBM evaluators cloning the repo will find `node_modules/` (hundreds of MB), `dist/`, `.env` secrets, and Python `__pycache__` committed. This is the fastest signal of professionalism or its absence.

**Expected Outcomes:**
- Root `.gitignore` covers `node_modules/`, `dist/`, `.env`, `__pycache__/`, `*.pyc`, `.venv/`, `baw/.venv/`
- A `digital-twin/.gitignore` is NOT needed separately — the root file covers the whole repo

**Todo List:**
1. Create `.gitignore` at the workspace root covering: `node_modules/`, `dist/`, `.env`, `*.pyc`, `__pycache__/`, `.venv/`, `*.egg-info`, `.DS_Store`, `*.log`

**Relevant Context:**
- `baw/.venv/` already has its own `.gitignore` but the root is missing entirely
- `digital-twin/.env.example` exists and should NOT be ignored (it documents the schema)

---

## Sub-Task B — Add CORS headers to the SSE `/stream` endpoint

**Status:** `[ ] pending`

**Intent:**
Flask does not emit `Access-Control-Allow-Origin` headers unless explicitly configured. The Vite dev proxy handles this locally, but in the IBM Cloud Code Engine production deployment the frontend and backend are on separate `.codeengine.appdomain.cloud` subdomains. Without CORS headers the browser silently kills the `EventSource` connection before the first byte arrives. This would cause the live demo to show `SIM MODE` even when the backend is live.

**Expected Outcomes:**
- `GET /stream` response includes `Access-Control-Allow-Origin: *` (acceptable for demo; a locked-down origin list would be used in real production)
- All other endpoints (`/infer`, `/health`, `/baw/trigger`) also send CORS headers so judges can call them directly from the browser console or Postman

**Todo List:**
1. Add `flask-cors>=4.0.0` to `pi-gnn/requirements.txt`
2. In `webhook_server.py`, import `CORS` from `flask_cors` and call `CORS(app)` directly after `app = Flask(__name__)` is defined

**Relevant Context:**
- `pi-gnn/webhook_server.py` line 51: `app = Flask(__name__)` — add `CORS(app)` on line 52
- `pi-gnn/requirements.txt` currently: `torch, flask, gunicorn, requests`
- The Vite proxy in `vite.config.js` lines 11–24 handles local dev, but CORS headers are needed for deployed production

---

## Sub-Task C — Fix the lazy BAW import and add `baw/__init__.py`

**Status:** `[ ] pending`

**Intent:**
`baw/watsonx_orchestrate_connector.py` line 386 imports `run_flood_response_workflow` inside the route handler at request time. If the import fails for any reason (wrong `sys.path`, syntax error, missing dep) the error surfaces mid-request, returning a 500 to the caller with no graceful fallback — and Code Engine's health check does not catch it at startup. Moving the import to the module top-level causes the container to fail fast at cold-start, where Code Engine will log the error cleanly.

An empty `baw/__init__.py` is also needed to mark `baw/` as a proper Python package, making the relative import unambiguous inside the Docker build context.

**Expected Outcomes:**
- `from baw_flood_response import run_flood_response_workflow` appears at the top of `watsonx_orchestrate_connector.py` (not inside a function)
- `baw/__init__.py` exists (can be empty or contain a one-line docstring)
- Container startup will fail loudly if `baw_flood_response.py` has any issue — caught by Code Engine health-check before any real traffic

**Todo List:**
1. Move the `from baw_flood_response import run_flood_response_workflow` import from inside `baw_trigger()` to the top-level imports section of `watsonx_orchestrate_connector.py` (after line 41, alongside the other imports)
2. Remove the now-redundant comment `# lazy import` from line 386
3. Create `baw/__init__.py` with a single docstring

**Relevant Context:**
- `baw/watsonx_orchestrate_connector.py` line 386 — current lazy import inside route
- `baw/watsonx_orchestrate_connector.py` lines 31–42 — imports section where the move goes

---

## Sub-Task D — Add a demo restart button (auto-loop)

**Status:** `[ ] pending`

**Intent:**
The simulation sequence in `App.jsx` plays once (stages 0–5) and then freezes. Stage 5 takes about 27 seconds total. A judge watching the screen for 30 seconds after stage 5 completes will see a frozen canvas and may assume the app crashed. Adding a "↺ Restart Demo" button in the header panel — and an auto-restart after a 10-second pause — keeps the demo alive during the judging period.

**Expected Outcomes:**
- After stage 5 animation completes (truck reaches end of reroute path), a 10-second countdown auto-restarts the sequence
- A "↺ Restart Demo" button in the header panel triggers an immediate reset at any time
- Restart resets: `stage=0`, `truckIndex=0`, `fleeingIndex` to initial value, `flowDepth/flowVel/manningN/hazardCoef` to normal values, `logs=[]`, `hazardSegments=[]`, `liveHazard=null`, `networkStatus=CONNECTED`, `containerState=IDLE`
- The `sequence()` async function re-runs after reset

**Todo List:**
1. Extract the initial metric values into constants at the top of `App.jsx`
2. Create a `resetDemo()` function that resets all relevant state to initial values and sets a trigger flag
3. Add a `restartTrigger` state (number, incremented on reset); pass it as a dep to the sequence `useEffect` so the sequence reruns
4. Add an auto-restart `useEffect` that watches for `stage === 5` and `truckIndex >= COORDS.nh544_reroute.length - 1`, then schedules a 10-second auto-reset
5. Add a "↺ Restart Demo" button in the header panel with `pointer-events: auto`

**Relevant Context:**
- `digital-twin/src/App.jsx` lines 101–150 — sequence `useEffect` with empty `[]` deps (must add `restartTrigger`)
- `digital-twin/src/App.jsx` lines 271–286 — header panel where button goes
- `digital-twin/src/index.css` lines 214–232 — `.container-status` pattern for button styling

---

## Sub-Task E — Show the reroute path as a distinct GeoJsonLayer

**Status:** `[ ] pending`

**Intent:**
During stage 5 the truck moves along `COORDS.nh544_reroute` (loaded from `routes.json`), but the WebGL canvas only shows the original route segments. The reroute path is rendered as a `ScatterplotLayer` of dots (lines 222–228 of `App.jsx`) — invisible at typical zoom levels. `routes.geojson` already contains `REROUTE-SEG-0` through `REROUTE-SEG-1274` features (1275 segments). Adding a second `GeoJsonLayer` for these segments — displayed green at stage >= 5 — makes the rerouting maneuver visually obvious.

**Expected Outcomes:**
- A second `GeoJsonLayer` with `id: 'nh544-reroute-path'` appears during stage >= 5, coloured `[0, 255, 157, 220]` (accent green)
- The original `ScatterplotLayer` of flooded-route dots (lines 222–228) is removed — it is superseded by the CRITICAL-coloured segments on the original GeoJsonLayer
- Judges see: red/flooded original route + green safe reroute = clear visual narrative

**Todo List:**
1. Add `reroute GeoJsonLayer` to the `layers` array in `App.jsx`, conditionally shown when `stage >= 5`, with `data: '/routes.geojson'`, filtering on `f.id.startsWith('REROUTE-')` via `getLineColor` returning transparent for non-reroute features and green for reroute features
2. Remove the `ScatterplotLayer` with `id: 'flooded-route-pts'` (lines 222–228) — it is visually inferior and now redundant
3. Update `getLineWidth` on the reroute layer to `5` pixels with a slight glow effect via opacity

**Relevant Context:**
- `digital-twin/src/App.jsx` lines 200–228 — current road layers
- `digital-twin/public/routes.geojson` — confirmed to contain `REROUTE-SEG-0` through `REROUTE-SEG-1274` with `segment_id` in properties
- Colour `[0, 255, 157, 220]` matches `--accent-green` in `index.css`

---

## Sub-Task F — Add segment click tooltips and 3D control hint

**Status:** `[ ] pending`

**Intent:**
The `GeoJsonLayer` has `pickable: true` but no `onClick` handler or `getTooltip`. If a judge clicks a road segment expecting to see hazard details, nothing happens. A simple click handler that calls `addLog()` with segment info — and a `getTooltip` for hover labels — turns a passive map into an interactive forensic tool. A one-line "Drag to orbit · Scroll to zoom" hint below the title also prevents judges from missing the 3D perspective controls.

**Expected Outcomes:**
- Clicking any `GeoJsonLayer` segment appends a log entry: `[SEGMENT] NH544-SEG-042 | hazard: 3.75 m²/s | CRITICAL`
- Hovering a segment shows a compact deck.gl tooltip with `segment_id` and `hazard_coefficient`
- The title subtitle in the header includes "Drag to orbit · Scroll to zoom" in the muted style

**Todo List:**
1. Add `onClick` prop to both GeoJsonLayers (road network and reroute) in `App.jsx` that calls `addLog` with segment properties
2. Pass `getTooltip` to `<DeckGL>` component (deck.gl's built-in tooltip renderer): returns `f.object?.properties.segment_id` + hazard
3. Add a subtitle hint string `"↕ Drag to orbit  ·  ⊕ Scroll to zoom"` to the header `<p>` tag next to the existing subtitle

**Relevant Context:**
- `digital-twin/src/App.jsx` lines 200–219 — `GeoJsonLayer` definition; add `onClick`
- `digital-twin/src/App.jsx` lines 261–263 — `<DeckGL>` component; add `getTooltip` prop
- `digital-twin/src/App.jsx` lines 272–275 — header title group; add hint

---

## Sub-Task G — Seed the PI-GNN model for deterministic demo outputs

**Status:** `[ ] pending`

**Intent:**
`PIGNN` is initialized with random PyTorch weights. The model is never trained, so inference output is numerically arbitrary. The hazard coefficient from `/infer` will be some unpredictable float — possibly very small (making `is_critical: false`) or very large — regardless of the input sensor values. This undermines the core "Physics-Informed" claim: the model should respond predictably to high-flood inputs (Sensor-NH544-B with depth=1.5, velocity=2.5) versus normal inputs. 

Fixing this with `torch.manual_seed(42)` before model instantiation makes the demo deterministic across cold-starts. Combined with a note in the README clarifying training intent, this converts a potential embarrassment into an honest architectural disclosure.

**Expected Outcomes:**
- `torch.manual_seed(42)` is called in `webhook_server.py` before `_MODEL = PIGNN(...)` is instantiated
- The same seed is noted in `model.py`'s `__main__` block so the standalone demo is also reproducible
- A comment in both places explains: "Seeded for reproducible demo output — replace with `load_state_dict()` for a trained model"
- README updated with one sentence in the PI-GNN section acknowledging the model is seeded for demo reproducibility

**Todo List:**
1. In `pi-gnn/webhook_server.py`, add `torch.manual_seed(42)` on the line before `_MODEL = PIGNN(...)`
2. In `pi-gnn/model.py` `__main__` block, add `torch.manual_seed(42)` before `model = PIGNN(...)`
3. Add a brief comment at both sites explaining the seed intent
4. Add one sentence to `README.md` Section 1 (PI-GNN) noting the demo seed

**Relevant Context:**
- `pi-gnn/webhook_server.py` line 55: `_MODEL = PIGNN(...)` — seed goes on line 54
- `pi-gnn/model.py` line 97: `model = PIGNN(...)` — seed goes on line 96
- `README.md` lines 14–16 — PI-GNN description section

---

## Sub-Task H — Add Mermaid architecture diagram to README

**Status:** `[ ] pending`

**Intent:**
The README has an excellent ASCII flow diagram (lines 140–158) but no visual architecture diagram showing the system topology — the IBM services, their relationships, and the data flows. A Mermaid diagram renders natively on GitHub and takes 30 seconds to read vs 3 minutes for the prose. IBM evaluators reviewing submissions on GitHub will form their first impression from this diagram.

**Expected Outcomes:**
- A `## 🗺️ System Architecture` section is inserted before the `## 💻 Getting Started` section
- The Mermaid diagram shows: Flood Sensors → Event Streams → Code Engine (PI-GNN) → SSE → Digital Twin; Code Engine → BAW → SMS/ERP/Warehouse; MCP Connector → watsonx Orchestrate
- Uses IBM product names explicitly (IBM Event Streams, IBM Cloud Code Engine, IBM watsonx Orchestrate)

**Todo List:**
1. Insert a new `## 🗺️ System Architecture` section in `README.md` before `## 💻 Getting Started`
2. Write a Mermaid `flowchart TD` diagram covering all five major components and their connections
3. Keep node labels short (fits in a standard GitHub preview width)

**Relevant Context:**
- `README.md` lines 50–56 — `## 💻 Getting Started` section starts here; new section goes before it
- The end-to-end ASCII flow at lines 140–158 can remain as the detailed supplement
