MCP_TOOL_REGISTRY = [
    {
        "name": "ksdma_infer",
        "description": (
            "Run PI-GNN inference on a single sensor telemetry payload using the "
            "Kinematic Stability Domain Mapping Algorithm (KSDMA). Returns the "
            "hazard coefficient (m²/s) and a boolean critical flag that triggers "
            "the BAW flood-response workflow when True."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["node_id", "depth", "velocity", "S0", "n"],
            "properties": {
                "node_id":  {"type": "string",  "description": "Sensor / node identifier, e.g. Sensor-NH544-A"},
                "depth":    {"type": "number",  "description": "Flow depth in metres"},
                "velocity": {"type": "number",  "description": "Flow velocity in m/s"},
                "S0":       {"type": "number",  "description": "Bed slope (dimensionless)"},
                "n":        {"type": "number",  "description": "Manning roughness coefficient"},
            },
        },
    },
    {
        "name": "event_streams_publish",
        "description": (
            "Publish a telemetry message directly to the IBM Event Streams "
            "(Kafka) chalakudy-basin-telemetry topic. Used by watsonx Orchestrate "
            "to inject synthetic test events or re-publish stale sensor data."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["node_id", "depth", "velocity", "S0", "n"],
            "properties": {
                "node_id":  {"type": "string"},
                "depth":    {"type": "number"},
                "velocity": {"type": "number"},
                "S0":       {"type": "number"},
                "n":        {"type": "number"},
            },
        },
    },
    {
        "name": "event_streams_latest_offset",
        "description": (
            "Query the latest committed Kafka offset for the "
            "chalakudy-basin-telemetry topic. Useful for auditing whether "
            "all sensor events have been processed before closing an incident."
        ),
        "inputSchema": {
            "type": "object",
            "required": [],
            "properties": {
                "partition": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "drone_dispatch",
        "description": (
            "Dispatch a reconnaissance UAV to the specified NH544 sector when cellular "
            "infrastructure fails and VDTN offline mode is active. Returns a structured "
            "dispatch confirmation including UAV type, flight path, and mission ID."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["node_id", "sector", "priority"],
            "properties": {
                "node_id":  {"type": "string",  "description": "VDTN node that entered the dead zone, e.g. Truck-FMCG-01"},
                "sector":   {"type": "string",  "description": "NH544 sector identifier, e.g. NH544_Sector7_Corridor"},
                "priority": {"type": "string",  "enum": ["emergency", "high", "normal"], "default": "emergency"},
                "uav_type": {"type": "string",  "description": "UAV model override (default: reconnaissance_quadcopter)"},
            },
        },
    },
]
