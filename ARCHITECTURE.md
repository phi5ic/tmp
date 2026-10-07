# Hydro-Kinematic Logistics Mesh: System Architecture & File Structure

This document outlines the high-level architecture and complete file system structure for the **Real-Time Flood Rerouting System (PI-GNN)**.

---

## 1. High-Level Architecture

The system is a distributed, event-driven mesh designed to monitor live flood telemetry, run physics-informed neural network (PI-GNN) inference, and push real-time alerts and visual updates to multiple clients (QGIS, Watsonx, Web HUD).

### Core Components

1. **PI-GNN Webhook Server (`pi-gnn/`)**
   - **Role**: The central brain of the system.
   - **Function**: Exposes a `/infer` webhook to receive live sensor data. Runs incoming data through a PyTorch-based Physics-Informed Graph Neural Network to compute flood hazard coefficients.
   - **Streaming**: Exposes a `/stream` endpoint using Server-Sent Events (SSE) to broadcast real-time inference results to all connected clients simultaneously.
   
2. **Telemetry / Sensor Emitter (`simulation/sensor_emitter.py`)**
   - **Role**: IoT Simulation.
   - **Function**: Simulates the VDTN (Vehicular Delay-Tolerant Network) and 5G sensor nodes along the NH544 corridor. It periodically POSTs synthetic telemetry (water level, velocity, mesh connection status) to the PI-GNN webhook.

3. **QGIS Real-Time Dashboard (`qgis-plugin/`)**
   - **Role**: Geospatial visualization.
   - **Function**: A custom PyQGIS plugin (`plugin_main.py`) that runs inside QGIS. It connects to the PI-GNN `/stream` SSE endpoint and dynamically updates the colours and properties of road segments (`LineStrings`) and sensor nodes in real time on top of an ESRI World Imagery basemap.

4. **Watsonx Orchestrate MCP Connector (`baw/`)**
   - **Role**: Enterprise integration.
   - **Function**: Exposes the KSDMA (Kinematic Stability Domain Mapping Algorithm) and IBM Event Streams publishing as an MCP (Model Context Protocol) JSON-RPC API. This allows Watsonx Orchestrate skill-flows to autonomously query flood status and trigger downstream business automation.

5. **Driver HUD Web UI (`driver-hud/`)**
   - **Role**: Logistics Fleet display.
   - **Function**: A lightweight, responsive web application for the FMCG truck drivers. It receives real-time alerts and displays dynamic route updates when the system determines a path is critically flooded.

---

## 2. File System Structure

```text
/home/phisync/github projects/2026 hackathon/
│
├── README.md                           # Main project documentation
├── DEMO_GUIDE.md                       # Step-by-step guide for running the demo stages
├── download_kerala.py                  # Script for fetching initial map boundaries
│
├── .bob/
│   └── mcp.json                        # MCP configuration for Watsonx / AI agents
│
├── baw/                                # Watsonx Orchestrate & Business Automation Workflows
│   ├── Dockerfile                      # Container definition for the connector
│   ├── requirements.txt
│   ├── baw_flood_response.py           # KSDMA orchestration workflow logic
│   └── watsonx_orchestrate_connector.py # MCP JSON-RPC Server & Event Streams publisher
│
├── driver-hud/                         # Logistics Fleet Web Dashboard
│   ├── index.html                      # Main driver UI
│   ├── app.js                          # Client-side logic for parsing SSE / alerts
│   ├── style.css                       # UI styling (dark mode, glassmorphism)
│   ├── manifest.json                   # PWA manifest
│   └── service-worker.js               # Service worker for offline VDTN caching
│
├── pi-gnn/                             # Backend Inference Engine
│   ├── main.py                         # Webhook server entry point (Flask)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── api/
│   │   ├── __init__.py
│   │   └── sse.py                      # Server-Sent Events manager
│   ├── core/
│   │   ├── __init__.py
│   │   ├── model.py                    # PyTorch PI-GNN definition and hazard math
│   │   └── router.py                   # Thread-safe routing & inference execution
│   └── integrations/
│       ├── __init__.py
│       └── vdtn_link.py                # Vehicular Delay-Tolerant Network simulator
│
├── qgis-plugin/                        # QGIS Integration
│   ├── plugin_main.py                  # Real-time QGIS SSE listener & layer updater
│   └── realtime_file_bridge.py         # File-based sync fallback mechanism
│
└── simulation/                         # Scenario Generation & QGIS Setup
    ├── generate_data.py                # Generates stage 0-5 GeoJSON datasets
    ├── build_qgis_project.py           # PyQGIS script to construct the base .qgz project
    ├── sensor_emitter.py               # The synthetic IoT telemetry daemon
    ├── hydro_kinematic_demo.qgz        # The generated QGIS Project file
    ├── styles/                         # QGIS Layer Style configurations (.qml)
    │   ├── route.qml
    │   ├── segment.qml
    │   └── sensor.qml
    └── data/                           # Generated GeoJSON features
        ├── nh544_original.geojson
        ├── nh544_reroute.geojson
        ├── flood_basin.geojson
        ├── sensor_nodes.geojson
        ├── vehicles.geojson
        ├── computed_reroute.geojson
        ├── routes_coords.json
        ├── routes_source.geojson
        └── routes_source_kerala.geojson
```
