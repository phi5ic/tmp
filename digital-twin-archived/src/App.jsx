import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Map, useControl } from 'react-map-gl/maplibre';
import { MapLibreOverlay } from '@deck.gl/maplibre';
import { GeoJsonLayer, ScatterplotLayer, PolygonLayer } from '@deck.gl/layers';
import { DataFilterExtension, PathStyleExtension } from '@deck.gl/extensions';
import { Radio, Server, RotateCcw, X } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';
import routesData from './routes.json';

// DeckGL overlay attached to the MapLibre map via react-map-gl's useControl hook.
// MapLibreOverlay handles its own resize / camera sync — no manual bookkeeping needed.
function DeckGLOverlay(props) {
  const overlay = useControl(() => new MapLibreOverlay(props));
  overlay.setProps(props);
  return null;
}

// Coordinates
const COORDS = {
  basin: [
    [10.32, 76.32], [10.35, 76.35], [10.34, 76.38], [10.30, 76.40], [10.28, 76.35]
  ],
  nh544_original: routesData.original,
  nh544_reroute: routesData.reroute
};

const hazardToColor = (hazard) => {
  if (hazard === null || hazard === undefined) return [0, 240, 255, 180];  // cyan
  if (hazard < 0.4)  return [0, 240, 255, 200];   // SAFE
  if (hazard < 0.8)  return [255, 170, 0,   220]; // WARNING
  return              [255, 51,  102, 255];       // CRITICAL
};

export default function App() {
  const [stage, setStage] = useState(0);
  const [logs, setLogs] = useState([]);
  
  // Metrics state
  const [flowDepth, setFlowDepth] = useState(0.2);
  const [flowVel, setFlowVel] = useState(0.5);
  const [manningN, setManningN] = useState(0.015);
  const [hazardCoef, setHazardCoef] = useState(0.1);
  const [networkStatus, setNetworkStatus] = useState('CONNECTED');
  const [containerState, setContainerState] = useState('IDLE');
  
  // Live SSE Hazard State
  const [hazardSegments, setHazardSegments] = useState([]);
  const [liveHazard, setLiveHazard] = useState(null);
  const [sseConnected, setSseConnected] = useState(false);

  // Entities state
  const [truckIndex, setTruckIndex] = useState(0);
  const [fleeingIndex, setFleeingIndex] = useState(COORDS.nh544_original.length - 1);

  // Segment click state — null when nothing selected
  const [selectedSegment, setSelectedSegment] = useState(null);

  // Orbit hint — shown once on first render, auto-dismissed after 4 s
  const [showOrbitHint, setShowOrbitHint] = useState(true);
  const [orbitHintFading, setOrbitHintFading] = useState(false);

  // Demo loop control — cancelled flag lets an in-flight sequence abort cleanly
  const cancelledRef = useRef(false);
  const sequenceRunningRef = useRef(false);
  
  const truckPos = stage >= 5 ? COORDS.nh544_reroute[truckIndex] : COORDS.nh544_original[truckIndex];
  const fleeingPos = COORDS.nh544_original[fleeingIndex];

  // SSE Listener for live backend binding
  // VITE_BACKEND_URL="" uses the Vite proxy; set to full URL for production
  useEffect(() => {
    const backendUrl = import.meta.env.VITE_BACKEND_URL || '';
    const eventSource = new EventSource(`${backendUrl}/stream`);
    let firstMessage = true;

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "HAZARD_UPDATE") {
          if (firstMessage) {
            addLog("[SSE CONNECTED] Live PI-GNN telemetry feed active.", "success");
            setSseConnected(true);
            firstMessage = false;
          }
          setHazardSegments(data.affected_segment_ids || []);
          setLiveHazard(data.hazard_coefficient);
          console.log("Live SSE Hazard Received:", data);
        }
      } catch (parseErr) {
        console.warn("SSE parse error:", parseErr);
      }
    };

    eventSource.onerror = () => {
      addLog("SSE: Connection to telemetry server lost — retrying...", "alert");
      setSseConnected(false);
    };

    return () => eventSource.close();
  }, []);

  // Smooth animation loop
  useEffect(() => {
    let interval;
    if (stage >= 1 && stage < 5) {
      interval = setInterval(() => {
        setTruckIndex(prev => Math.min(prev + 1, Math.floor(COORDS.nh544_original.length * 0.23)));
        setFleeingIndex(prev => Math.max(prev - 2, Math.floor(COORDS.nh544_original.length * 0.28)));
      }, 50);
    } else if (stage === 5) {
      interval = setInterval(() => {
        setTruckIndex(prev => Math.min(prev + 2, COORDS.nh544_reroute.length - 1));
      }, 50);
    }
    return () => clearInterval(interval);
  }, [stage]);

  const addLog = useCallback((msg, type = 'info') => {
    setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), msg, type }]);
  }, []);

  // Resets all demo state back to initial values
  const resetState = useCallback(() => {
    setStage(0);
    setLogs([]);
    setFlowDepth(0.2);
    setFlowVel(0.5);
    setManningN(0.015);
    setHazardCoef(0.1);
    setNetworkStatus('CONNECTED');
    setContainerState('IDLE');
    setHazardSegments([]);
    setLiveHazard(null);
    setTruckIndex(0);
    setFleeingIndex(COORDS.nh544_original.length - 1);
    setSelectedSegment(null);
  }, []);

  // Orbit hint — fade out after 4 s, remove from DOM after transition completes
  useEffect(() => {
    const fadeTimer  = setTimeout(() => setOrbitHintFading(true),  4000);
    const removeTimer = setTimeout(() => setShowOrbitHint(false),  4600);
    return () => { clearTimeout(fadeTimer); clearTimeout(removeTimer); };
  }, []);

  // Segment layer click handler — toggle selection on same segment, set new one otherwise
  const handleSegmentClick = useCallback((info) => {
    if (!info.object) { setSelectedSegment(null); return; }
    const { segment_id, hazard_coefficient, is_critical } = info.object.properties;
    const isReroute = segment_id?.startsWith('REROUTE-SEG-');
    setSelectedSegment(prev =>
      prev?.segmentId === segment_id
        ? null   // clicking same segment again closes the panel
        : { segmentId: segment_id, isReroute, hazardCoef: hazard_coefficient, isCritical: is_critical,
            x: info.x, y: info.y }
    );
  }, []);

  // Dismiss segment panel on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setSelectedSegment(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Cancellable sleep — resolves immediately when cancelledRef flips true
  const sleep = useCallback((ms) => {
    return new Promise(resolve => {
      const id = setTimeout(resolve, ms);
      const poll = setInterval(() => {
        if (cancelledRef.current) { clearTimeout(id); clearInterval(poll); resolve(); }
      }, 50);
      setTimeout(() => clearInterval(poll), ms + 100);
    });
  }, []);

  const runSequence = useCallback(async () => {
    if (sequenceRunningRef.current) return;
    sequenceRunningRef.current = true;
    cancelledRef.current = false;

    const log = (msg, type = 'info') =>
      !cancelledRef.current && setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), msg, type }]);

    log("IBM Bob Orchestrator Initialized.", "info");
    log("Subscribing to PI-GNN Event Streams...", "info");

    await sleep(3000); if (cancelledRef.current) { sequenceRunningRef.current = false; return; }

    setStage(1);
    log("FMCG Fleet 01 en route via NH544.", "info");

    await sleep(6000); if (cancelledRef.current) { sequenceRunningRef.current = false; return; }

    setStage(2);
    setContainerState('SCALING');
    log("IBM Code Engine: Scaling up serverless PI-GNN containers...", "info");
    log("WARNING: Unpredicted cloudburst detected in Chalakudy Basin.", "alert");
    setManningN(0.065);
    setFlowDepth(1.4);
    setFlowVel(2.2);
    log("Hydrodynamic SIM: Manning's n increased to 0.065 (Debris flow).", "alert");

    await sleep(6000); if (cancelledRef.current) { sequenceRunningRef.current = false; return; }
    setContainerState('INFERENCING');

    setStage(3);
    setNetworkStatus('VDTN_ACTIVE');
    log("CRITICAL: Cellular infrastructure failure at Sector 7.", "alert");
    log("Node FMCG-01 switching to VDTN offline mode.", "alert");
    log("MCP: drone_dispatch → reconnaissance_quadcopter → NH544_Sector7_Corridor [EMERGENCY]", "info");

    await sleep(6000); if (cancelledRef.current) { sequenceRunningRef.current = false; return; }

    setStage(4);
    setHazardCoef(1.4 * 2.2);
    log("VDTN Handshake Established: FMCG-01 <-> Fleeing-02.", "success");
    log("Telemetry received. Calculating Kinematic Stability Matrix...", "info");

    await sleep(2000); if (cancelledRef.current) { sequenceRunningRef.current = false; return; }
    log("Hazard Coefficient = 3.03 m²/s (> 0.8 threshold).", "alert");

    await sleep(4000); if (cancelledRef.current) { sequenceRunningRef.current = false; return; }

    setStage(5);
    log("PI-GNN: Executing offline rerouting maneuver.", "success");
    log("Watsonx ERP Alert sent to Fleet Manager.", "info");
    setContainerState('IDLE');

    sequenceRunningRef.current = false;

    // ── Auto-loop: 5-second countdown then restart ────────────────────────────
    for (let i = 5; i >= 1; i--) {
      await sleep(1000); if (cancelledRef.current) return;
      setLogs(prev => [...prev, {
        time: new Date().toLocaleTimeString(),
        msg: `Demo restarting in ${i}…`,
        type: 'countdown',
      }]);
    }
    await sleep(1000); if (cancelledRef.current) return;

    resetState();
    // Small gap so the state flush paints before the next sequence starts
    await sleep(200);
    runSequence();
  }, [sleep, resetState]);

  // Restart button handler — cancel in-flight sequence, reset, re-run
  const handleRestart = useCallback(() => {
    cancelledRef.current = true;
    sequenceRunningRef.current = false;
    resetState();
    // Yield one tick so state flush completes, then kick off fresh sequence
    setTimeout(() => {
      cancelledRef.current = false;
      runSequence();
    }, 50);
  }, [resetState, runSequence]);

  useEffect(() => {
    runSequence();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const logsEndRef = useRef(null);
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Deck.GL Layers — basemap is now MapLibre underneath; no TileLayer needed
  const layers = [
    // Hazard Basin Polygon
    stage >= 2 && new PolygonLayer({
      id: 'basin-polygon',
      data: [{ polygon: COORDS.basin.map(c => [c[1], c[0]]) }], // [lng, lat]
      getPolygon: d => d.polygon,
      getFillColor: [255, 51, 102, 100],
      getLineColor: [255, 51, 102, 255],
      getLineWidth: 2,
      lineWidthUnits: 'pixels',
      filled: true
    }),

    // Cloudburst Heatmap Radius
    stage >= 2 && new ScatterplotLayer({
      id: 'cloudburst-heatmap',
      data: [{ position: [76.36, 10.33] }],
      getPosition: d => d.position,
      getFillColor: [255, 51, 102, 30],
      getRadius: 2500,
      stroked: true,
      getLineColor: [255, 51, 102, 150],
      getLineWidth: 2,
      lineWidthUnits: 'pixels'
    }),

    // Original NH544 road network — hazard-coloured via PI-GNN SSE; fades to red
    // at stage >= 5 to show the flooded / severed route.
    new GeoJsonLayer({
      id: 'nh544-original',
      data: '/routes.geojson',
      pickable: true,
      stroked: true,
      filled: false,
      // Filter to ORIG segments only; REROUTE segments handled by the layer below
      extensions: [new DataFilterExtension({ filterSize: 1 })],
      getFilterValue: f => f.properties.segment_id?.startsWith('ORIG-SEG-') ? 1 : 0,
      filterRange: [1, 1],
      getLineColor: f => {
        if (selectedSegment?.segmentId === f.properties.segment_id)
          return [255, 255, 255, 255]; // selected: bright white highlight
        if (stage >= 5) return [255, 51, 102, 80];
        if (hazardSegments.includes(f.properties.segment_id))
          return hazardToColor(liveHazard || hazardCoef);
        return [0, 240, 255, 120];
      },
      getLineWidth: f => {
        if (selectedSegment?.segmentId === f.properties.segment_id) return 8;
        if (stage >= 5) return 2;
        return hazardSegments.includes(f.properties.segment_id) ? 6 : 3;
      },
      lineWidthUnits: 'pixels',
      onClick: handleSegmentClick,
      updateTriggers: {
        getLineColor: [stage, hazardSegments, liveHazard, hazardCoef, selectedSegment?.segmentId],
        getLineWidth:  [stage, hazardSegments, selectedSegment?.segmentId],
      }
    }),

    // Reroute path — only rendered from stage 5 onward, distinct green dashed line
    stage >= 5 && new GeoJsonLayer({
      id: 'nh544-reroute',
      data: '/routes.geojson',
      pickable: true,
      stroked: true,
      filled: false,
      extensions: [
        new DataFilterExtension({ filterSize: 1 }),
        new PathStyleExtension({ dash: true }),
      ],
      getFilterValue: f => f.properties.segment_id?.startsWith('REROUTE-SEG-') ? 1 : 0,
      filterRange: [1, 1],
      getLineColor: f =>
        selectedSegment?.segmentId === f.properties.segment_id
          ? [255, 255, 255, 255]
          : [0, 255, 157, 230],
      getLineWidth: f =>
        selectedSegment?.segmentId === f.properties.segment_id ? 8 : 5,
      lineWidthUnits: 'pixels',
      getDashArray: [6, 3],
      dashJustified: true,
      onClick: handleSegmentClick,
      updateTriggers: {
        getLineColor: [stage, selectedSegment?.segmentId],
        getLineWidth:  [selectedSegment?.segmentId],
      }
    }),

    // Fleeing Vehicle (VDTN Node) - Scaled properly in pixels!
    stage >= 2 && stage < 5 && new ScatterplotLayer({
      id: 'fleeing-vehicle',
      data: [{ position: [fleeingPos[1], fleeingPos[0]] }],
      getPosition: d => d.position,
      getFillColor: [255, 170, 0, 255], // Amber
      getRadius: 14,
      radiusUnits: 'pixels',
      stroked: true,
      getLineColor: [255, 255, 255, 255],
      getLineWidth: 2,
      lineWidthUnits: 'pixels'
    }),

    // Main FMCG Truck - Scaled properly in pixels!
    new ScatterplotLayer({
      id: 'fmcg-truck',
      data: [{ position: [truckPos[1], truckPos[0]] }],
      getPosition: d => d.position,
      getFillColor: networkStatus === 'CONNECTED' ? [0, 255, 157, 255] : [255, 255, 255, 255], // Cyan / White
      getRadius: 18,
      radiusUnits: 'pixels',
      stroked: true,
      getLineColor: [0, 0, 0, 255],
      getLineWidth: 3,
      lineWidthUnits: 'pixels'
    })
  ];

  // deck.gl hover tooltip — returned as HTML string from getTooltip
  const getTooltip = useCallback((info) => {
    if (!info.object?.properties) return null;
    const { segment_id, hazard_coefficient } = info.object.properties;
    const isReroute = segment_id?.startsWith('REROUTE-SEG-');
    const hazard = hazard_coefficient ?? 0;
    const statusLabel = hazard > 0.8 ? 'CRITICAL' : hazard > 0.4 ? 'WARNING' : 'SAFE';
    const statusColor = hazard > 0.8 ? '#ff3366' : hazard > 0.4 ? '#ffde00' : '#00ff9d';
    return {
      html: `
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.6">
          <div style="color:#94a3b8;margin-bottom:2px">${isReroute ? '🟢 REROUTE PATH' : '🔵 ORIG ROUTE'}</div>
          <div style="color:#f0f4f8;font-weight:700">${segment_id}</div>
          <div style="color:${statusColor};margin-top:2px">${statusLabel} · ${hazard.toFixed(3)} m²/s</div>
          <div style="color:#94a3b8;font-size:10px;margin-top:3px">Click to inspect</div>
        </div>`,
      style: {
        background: 'rgba(11,15,25,0.92)',
        border: `1px solid ${statusColor}44`,
        borderRadius: '8px',
        padding: '8px 12px',
        color: '#f0f4f8',
        boxShadow: '0 4px 16px rgba(0,0,0,0.7)',
        pointerEvents: 'none',
      }
    };
  }, []);

  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <Map
        initialViewState={{ longitude: 76.35, latitude: 10.32, zoom: 12, pitch: 45, bearing: 0 }}
        style={{ width: '100%', height: '100%' }}
        mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        onClick={(e) => { if (!e.features?.length) setSelectedSegment(null); }}
      >
        <DeckGLOverlay
          layers={layers}
          getTooltip={getTooltip}
          onClick={(info) => { if (!info.object) setSelectedSegment(null); }}
        />
      </Map>

      {/* ── Orbit hint ── */}
      {showOrbitHint && (
        <div className={`orbit-hint${orbitHintFading ? ' fading' : ''}`}>
          Drag to orbit · Scroll to zoom · Right-drag to pan
        </div>
      )}

      {/* ── Segment inspector panel ── */}
      {selectedSegment && (
        <div
          className="segment-panel"
          style={{ left: Math.min(selectedSegment.x + 12, window.innerWidth - 240), top: Math.min(selectedSegment.y - 12, window.innerHeight - 160) }}
        >
          <div className="segment-panel-header">
            <span className={`segment-type-badge ${selectedSegment.isReroute ? 'reroute' : 'orig'}`}>
              {selectedSegment.isReroute ? 'REROUTE PATH' : 'ORIG ROUTE'}
            </span>
            <button className="segment-close" onClick={() => setSelectedSegment(null)} title="Close">
              <X size={12} />
            </button>
          </div>
          <div className="segment-id">{selectedSegment.segmentId}</div>
          <div className="segment-rows">
            <div className="segment-row">
              <span className="segment-label">Hazard Coef</span>
              <span className={`segment-value ${selectedSegment.isCritical ? 'danger' : 'safe'}`}>
                {(selectedSegment.hazardCoef ?? 0).toFixed(3)} m²/s
              </span>
            </div>
            <div className="segment-row">
              <span className="segment-label">Status</span>
              <span className={`segment-value ${selectedSegment.isCritical ? 'danger' : 'safe'}`}>
                {selectedSegment.isCritical ? 'CRITICAL' : 'SAFE'}
              </span>
            </div>
            <div className="segment-row">
              <span className="segment-label">Type</span>
              <span className="segment-value" style={{ color: 'var(--text-muted)' }}>
                {selectedSegment.isReroute ? 'PI-GNN Reroute' : 'Original NH544'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* UI Overlay */}
      <div className="ui-layer" style={{ pointerEvents: 'none', zIndex: 10, position: 'absolute' }}>
        <div className="panel header-panel">
          <div className="title-group">
            <h1>Hydro-Kinematic Logistics Mesh</h1>
            <p>deck.gl WebGL | IBM Event Streams | PI-GNN</p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <div className={`status-badge ${stage >= 3 ? 'critical' : ''}`}>
              <div className="status-dot"></div>
              {networkStatus === 'CONNECTED' ? 'LTE/5G CONNECTED' : 'VDTN OFFLINE MODE'}
            </div>
            <div className={`container-status ${containerState === 'SCALING' ? 'scaling' : ''}`}>
              <Server size={12} />
              IBM Code Engine: {containerState}
            </div>
            <div className={`live-badge ${sseConnected ? 'live' : 'sim'}`}>
              <span className="live-dot"></span>
              {sseConnected ? 'LIVE TELEMETRY' : 'SIM MODE'}
            </div>
          </div>
        </div>

        <div className="bottom-panels">
          <div className="panel metrics-panel">
            <div className="metric-card">
              <div className="metric-title">Flow Depth (y)</div>
              <div className={`metric-value ${stage >= 2 ? 'danger' : 'safe'}`}>{flowDepth.toFixed(2)} m</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Flow Velocity (V)</div>
              <div className={`metric-value ${stage >= 2 ? 'danger' : 'safe'}`}>{flowVel.toFixed(2)} m/s</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Manning's Roughness (n)</div>
              <div className={`metric-value ${stage >= 2 ? 'warning' : 'safe'}`}>{manningN.toFixed(3)}</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">
                Hazard Coef (y × V)
                {sseConnected && <span className="live-inline-tag">LIVE</span>}
              </div>
              <div className={`metric-value ${(liveHazard ?? hazardCoef) > 0.8 ? 'danger' : 'safe'}`}>
                {(liveHazard ?? hazardCoef).toFixed(2)} m²/s
              </div>
            </div>
          </div>

          <div className="panel log-panel">
            <div className="log-header">
              <span>MCP Agent / Orchestrator Logs</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Radio size={16} className={stage >= 3 ? 'text-accent-red' : 'text-accent-cyan'} />
                <button className="btn-restart" onClick={handleRestart} title="Restart demo">
                  <RotateCcw size={13} />
                  Restart
                </button>
              </div>
            </div>
            <div className="log-content">
              {logs.map((entry, i) => (
                <div key={i} className={`log-entry ${entry.type}`}>
                  <span style={{color: 'var(--text-muted)'}}>[{entry.time}]</span> {entry.msg}
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
