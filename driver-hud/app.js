// ═══════════════════════════════════════════════════════════════════════════════
// PI-GNN Driver HUD — Real-Time Frontend Application
// Backend: Flask SSE server at /stream, /report, /start_sim, /route_coords
// ═══════════════════════════════════════════════════════════════════════════════

const SERVER_URL = "http://localhost:8080";
const SSE_URL    = `${SERVER_URL}/stream`;
const AVG_SPEED_KMH = 40;

// ── DOM Elements ──────────────────────────────────────────────────────────────
const els = {
    overallStatus:    document.getElementById('overall-status'),
    stageLabel:       document.getElementById('stage-label'),
    rerouteAlert:     document.getElementById('reroute-alert'),
    alertDetail:      document.getElementById('alert-detail'),
    hazardVal:        document.getElementById('hazard-val'),
    depthVal:         document.getElementById('depth-val'),
    velocityVal:      document.getElementById('velocity-val'),
    manningVal:       document.getElementById('manning-val'),
    affectedVal:      document.getElementById('affected-val'),
    stageVal:         document.getElementById('stage-val'),
    eventFeed:        document.getElementById('event-feed'),
    connectionDot:    document.getElementById('connection-dot'),
    v2vList:          document.getElementById('v2v-list'),
    liveIndicator:    document.getElementById('live-indicator'),
    mapDistance:      document.getElementById('map-distance'),
    mapEta:           document.getElementById('map-eta'),
    mapHazard:        document.getElementById('map-hazard'),
    mapRouteBadge:    document.getElementById('map-route-badge'),
    mapNetworkBadge:  document.getElementById('map-network-badge'),
    btnTtsToggle:     document.getElementById('btn-tts-toggle'),
    ttsIcon:          document.getElementById('tts-icon'),
    btnSimRestart:    document.getElementById('btn-sim-restart'),
    metricHazard:     document.getElementById('metric-hazard'),
    metricDepth:      document.getElementById('metric-depth'),
    metricVelocity:   document.getElementById('metric-velocity'),
    metricManning:    document.getElementById('metric-manning'),
    metricAffected:   document.getElementById('metric-affected'),
    // Navigation panel elements
    navDistance:      document.getElementById('nav-distance'),
    navEta:           document.getElementById('nav-eta'),
    navSpeed:         document.getElementById('nav-speed'),
    navBearing:       document.getElementById('nav-bearing'),
    navNextWaypoint:  document.getElementById('nav-next-waypoint'),
    navRouteStatus:   document.getElementById('nav-route-status'),
    navProgress:      document.getElementById('nav-progress'),
    navProgressBar:   document.getElementById('nav-progress-bar'),
};

// ── Application State ─────────────────────────────────────────────────────────
let ttsEnabled      = true;
let currentSeverity = "SAFE";
let currentStage    = -1;
let isRerouted      = false;
let reportType      = 'flood';
let reportSeverity  = 1;

// Map state
let map                  = null;
let routeLayerOriginal   = null;
let routeLayerReroute    = null;
let truckMarker          = null;
let floodZoneLayer       = null;
let reportMarkers        = [];
let routeCoords          = { original: [], reroute: [] };
let routeArrowDecorator  = null;

// Navigation state
let currentRouteCoords   = [];   // active route coords [[lat, lon], ...]
let truckAnimIndex       = 0;
let truckAnimInterval    = null;
let truckLatLng          = [10.249946, 76.319778];
let totalRouteLengthM    = 29390.3;
let distanceCoveredM     = 0;
let navUpdateInterval    = null;

// SSE connection
let eventSource = null;

// ── Utilities ─────────────────────────────────────────────────────────────────
function getTimeStr() {
    return new Date().toLocaleTimeString([], { hour12: false });
}

function addLog(msg, type = 'info') {
    const li = document.createElement('li');
    li.className = type;
    li.innerHTML = `<span class="time">[${getTimeStr()}]</span> ${msg}`;
    els.eventFeed.prepend(li);
    if (els.eventFeed.children.length > 80) els.eventFeed.lastChild.remove();
}

function haversineMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

function calcRouteLength(coords) {
    // coords: [[lat, lon], ...]
    let total = 0;
    for (let i = 0; i < coords.length - 1; i++) {
        total += haversineMeters(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1]);
    }
    return total;
}

function calcBearing(lat1, lon1, lat2, lon2) {
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const rlat1 = lat1 * Math.PI / 180;
    const rlat2 = lat2 * Math.PI / 180;
    const y = Math.sin(dLon) * Math.cos(rlat2);
    const x = Math.cos(rlat1) * Math.sin(rlat2) - Math.sin(rlat1) * Math.cos(rlat2) * Math.cos(dLon);
    const bearing = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
    return bearing;
}

function bearingToCardinal(deg) {
    const dirs = ['N','NE','E','SE','S','SW','W','NW'];
    return dirs[Math.round(deg / 45) % 8];
}

function updateEta(lengthM) {
    const speedMps = (AVG_SPEED_KMH * 1000) / 3600;
    const minutes  = Math.round(lengthM / speedMps / 60);
    if (els.mapEta) els.mapEta.textContent = `${minutes} min`;
    if (els.navEta) els.navEta.textContent = `${minutes} min`;
    return minutes;
}

function updateSeverityColors(severity) {
    currentSeverity = severity;
    els.overallStatus.className = 'status-badge ' + severity;
    els.overallStatus.textContent = severity;

    const hazardEl = els.mapHazard;
    if (severity === 'CRITICAL') {
        hazardEl.style.color = 'var(--color-critical)';
    } else if (severity === 'WARNING') {
        hazardEl.style.color = 'var(--color-warning)';
    } else {
        hazardEl.style.color = 'var(--color-safe)';
    }

    const metricClass = severity === 'CRITICAL' ? 'critical' : severity === 'WARNING' ? 'warning' : '';
    [els.metricHazard, els.metricDepth, els.metricVelocity].forEach(m => {
        m.className = 'metric ' + metricClass;
    });

    const colorVar = severity === 'CRITICAL' ? 'var(--color-critical)' :
                     severity === 'WARNING'  ? 'var(--color-warning)'  :
                     'var(--color-safe)';
    els.hazardVal.style.color  = colorVar;
    els.depthVal.style.color   = colorVar;
    els.velocityVal.style.color = colorVar;

    els.connectionDot.style.background = colorVar;
    els.connectionDot.style.boxShadow  = `0 0 12px ${colorVar}`;
}

// ── Navigation Panel ──────────────────────────────────────────────────────────

function updateNavPanel() {
    if (!currentRouteCoords || currentRouteCoords.length < 2) return;

    const truck = truckMarker ? truckMarker.getLatLng() : { lat: truckLatLng[0], lng: truckLatLng[1] };

    // Find nearest point index on route
    let nearestIdx = 0;
    let nearestDist = Infinity;
    for (let i = 0; i < currentRouteCoords.length; i++) {
        const d = haversineMeters(truck.lat, truck.lng, currentRouteCoords[i][0], currentRouteCoords[i][1]);
        if (d < nearestDist) {
            nearestDist = d;
            nearestIdx  = i;
        }
    }

    // Remaining distance from nearest point to end
    let remaining = 0;
    for (let i = nearestIdx; i < currentRouteCoords.length - 1; i++) {
        remaining += haversineMeters(
            currentRouteCoords[i][0], currentRouteCoords[i][1],
            currentRouteCoords[i+1][0], currentRouteCoords[i+1][1]
        );
    }

    const covered      = totalRouteLengthM - remaining;
    const progressPct  = Math.min(100, Math.round((covered / totalRouteLengthM) * 100));
    const remainKm     = (remaining / 1000).toFixed(1);
    const minutes      = Math.round(remaining / ((AVG_SPEED_KMH * 1000) / 3600) / 60);

    // Next waypoint
    const nextIdx = Math.min(nearestIdx + 5, currentRouteCoords.length - 1);
    const next    = currentRouteCoords[nextIdx];

    // Bearing to next waypoint
    const bearing  = calcBearing(truck.lat, truck.lng, next[0], next[1]);
    const cardinal = bearingToCardinal(bearing);

    if (els.navDistance)    els.navDistance.textContent    = `${remainKm} km`;
    if (els.navEta)         els.navEta.textContent         = `${minutes} min`;
    if (els.navSpeed)       els.navSpeed.textContent       = `${AVG_SPEED_KMH} km/h`;
    if (els.navBearing)     els.navBearing.textContent     = `${Math.round(bearing)}° ${cardinal}`;
    if (els.navNextWaypoint) els.navNextWaypoint.textContent = `${next[0].toFixed(4)}°N, ${next[1].toFixed(4)}°E`;
    if (els.navProgress)    els.navProgress.textContent    = `${progressPct}%`;
    if (els.navProgressBar) els.navProgressBar.style.width = `${progressPct}%`;
    if (els.navRouteStatus) {
        els.navRouteStatus.textContent = isRerouted ? 'DIVERTED' : 'ON ROUTE';
        els.navRouteStatus.className   = 'nav-route-status ' + (isRerouted ? 'diverted' : 'on-route');
    }

    // Also sync map overlay
    if (els.mapDistance) els.mapDistance.textContent = `${remainKm} km`;
    if (els.mapEta)      els.mapEta.textContent      = `${minutes} min`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// TTS (Text-to-Speech) System
// ═══════════════════════════════════════════════════════════════════════════════

function speak(text, urgent = false) {
    if (!ttsEnabled) return;
    if (!('speechSynthesis' in window)) return;

    if (urgent) window.speechSynthesis.cancel();

    const utterance  = new SpeechSynthesisUtterance(text);
    utterance.rate   = urgent ? 1.05 : 0.95;
    utterance.pitch  = urgent ? 1.15 : 1.0;
    utterance.volume = 1.0;
    utterance.lang   = 'en-US';

    const voices    = window.speechSynthesis.getVoices();
    const preferred = voices.find(v =>
        v.name.includes('Google') || v.name.includes('Samantha') || v.name.includes('Microsoft'));
    if (preferred) utterance.voice = preferred;

    window.speechSynthesis.speak(utterance);
}

if ('speechSynthesis' in window) {
    speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();
}

els.btnTtsToggle.addEventListener('click', () => {
    ttsEnabled = !ttsEnabled;
    els.ttsIcon.textContent = ttsEnabled ? '🔊' : '🔇';
    addLog(`Voice alerts ${ttsEnabled ? 'enabled' : 'disabled'}.`, 'info');
});

// ═══════════════════════════════════════════════════════════════════════════════
// LEAFLET MAP
// ═══════════════════════════════════════════════════════════════════════════════

function initMap() {
    map = L.map('map', {
        center: [10.31, 76.37],
        zoom: 12,
        zoomControl: true,
        attributionControl: true,
    });

    // Dark tile layer — CartoDB Dark Matter via unpkg CDN proxy
    // Works correctly when served from http://localhost (file:// was the issue)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
        subdomains: 'abcd',
        maxZoom: 20,
    }).addTo(map);

    // Origin marker
    const originIcon = L.divIcon({
        className: '',
        html: '<div style="width:16px;height:16px;background:#00f0ff;border-radius:50%;border:2px solid #fff;box-shadow:0 0 14px #00f0ff;"></div>',
        iconSize: [16, 16], iconAnchor: [8, 8],
    });
    L.marker([10.249946, 76.319778], { icon: originIcon })
        .addTo(map)
        .bindPopup('<b style="color:#00f0ff">ORIGIN</b><br>Cochin Hub 01<br><small>NH544 Departure</small>');

    // Destination marker
    const destIcon = L.divIcon({
        className: '',
        html: '<div style="width:16px;height:16px;background:#00ff9d;border-radius:50%;border:2px solid #fff;box-shadow:0 0 14px #00ff9d;"></div>',
        iconSize: [16, 16], iconAnchor: [8, 8],
    });
    L.marker([10.379903, 76.390489], { icon: destIcon })
        .addTo(map)
        .bindPopup('<b style="color:#00ff9d">DESTINATION</b><br>Thrissur Terminal<br><small>NH544 Arrival</small>');

    // Sensor markers
    const sensorIcon = L.divIcon({
        className: '',
        html: '<div style="width:10px;height:10px;background:#ffaa00;border-radius:2px;border:1.5px solid #fff;transform:rotate(45deg);box-shadow:0 0 8px #ffaa00;"></div>',
        iconSize: [10, 10], iconAnchor: [5, 5],
    });
    L.marker([10.3100, 76.3900], { icon: sensorIcon })
        .addTo(map)
        .bindPopup('<b style="color:#ffaa00">Sensor-NH544-A</b><br>Approach zone monitoring');
    L.marker([10.3050, 76.3700], { icon: sensorIcon })
        .addTo(map)
        .bindPopup('<b style="color:#ffaa00">Sensor-NH544-B</b><br>Flood zone — Chalakudy Bridge');

    // Truck marker
    const truckIcon = L.divIcon({
        className: 'truck-marker',
        html: '<div style="font-size:22px;filter:drop-shadow(0 0 8px rgba(0,240,255,0.9));transform:translate(-3px,-3px);">🚚</div>',
        iconSize: [28, 28], iconAnchor: [14, 14],
    });
    truckMarker = L.marker([10.249946, 76.319778], { icon: truckIcon, zIndexOffset: 1000 })
        .addTo(map)
        .bindPopup('<b style="color:#00f0ff">TRK-774-X</b><br>FMCG Fleet 01<br><small>Live GPS tracking</small>');

    loadRouteCoords();
}

async function loadRouteCoords() {
    try {
        const res = await fetch(`${SERVER_URL}/route_coords`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        routeCoords = await res.json();
        addLog(`Route loaded: ${routeCoords.original.length} original + ${routeCoords.reroute.length} reroute waypoints.`, 'info');
    } catch (e) {
        addLog(`Could not load route from server (${e.message}). Using fallback coords.`, 'warning');
        routeCoords = {
            original: [
                [10.249946, 76.319778],[10.262, 76.332],[10.270, 76.348],
                [10.285, 76.360],[10.300, 76.370],[10.315, 76.375],
                [10.330, 76.380],[10.350, 76.390],[10.365, 76.391],
                [10.379903, 76.390489]
            ],
            reroute: [
                [10.249946, 76.319778],[10.262, 76.332],[10.270, 76.348],
                [10.275, 76.342],[10.283, 76.338],[10.296, 76.340],
                [10.315, 76.352],[10.330, 76.365],[10.344, 76.377],
                [10.358, 76.388],[10.370, 76.391],[10.379903, 76.390489]
            ]
        };
    }

    // Draw original route and set as active
    currentRouteCoords = routeCoords.original;
    totalRouteLengthM  = calcRouteLength(currentRouteCoords);
    drawOriginalRoute();
    updateNavPanel();
}

function drawOriginalRoute() {
    if (routeLayerOriginal) map.removeLayer(routeLayerOriginal);

    const coords = routeCoords.original.map(c => Array.isArray(c) ? [c[0], c[1]] : [c.lat, c.lng]);
    routeLayerOriginal = L.polyline(coords, {
        color: '#00f0ff',
        weight: 5,
        opacity: 0.85,
        lineCap: 'round',
        lineJoin: 'round',
    }).addTo(map);

    routeLayerOriginal.bindTooltip('NH544 — Original Route', { sticky: true });

    try {
        map.fitBounds(routeLayerOriginal.getBounds(), { padding: [40, 40] });
    } catch(_) {}
}

function drawRerouteRoute(coordsOverride) {
    // Dim original route to show it's blocked
    if (routeLayerOriginal) {
        routeLayerOriginal.setStyle({ color: '#ff3366', weight: 3, opacity: 0.45, dashArray: '8, 6' });
    }

    if (routeLayerReroute) map.removeLayer(routeLayerReroute);

    // Use server-provided coordinates if available, otherwise fall back
    let coords;
    if (coordsOverride && coordsOverride.length > 0) {
        // Server returns [lon, lat] — convert to [lat, lon] for Leaflet
        coords = coordsOverride.map(c => [c[1], c[0]]);
    } else {
        coords = routeCoords.reroute.map(c => Array.isArray(c) ? [c[0], c[1]] : [c.lat, c.lng]);
    }

    routeLayerReroute = L.polyline(coords, {
        color: '#00ff9d',
        weight: 6,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round',
    }).addTo(map);

    routeLayerReroute.bindTooltip('⚡ PI-GNN Safe Reroute (A*)', { sticky: true });

    // Update active route coords for navigation
    currentRouteCoords = coords;
    totalRouteLengthM  = calcRouteLength(coords);
    distanceCoveredM   = 0;

    // Pan to show reroute
    try {
        map.fitBounds(routeLayerReroute.getBounds(), { padding: [40, 40] });
    } catch(_) {}

    // Animate truck on reroute
    stopTruckAnimation();
    startTruckAnimation(true, coords);
}

function updateRerouteFromCoords(serverCoords) {
    // Called when REROUTE_UPDATE has live coordinates from server
    if (!serverCoords || serverCoords.length === 0) return;
    // serverCoords: [[lon, lat], ...]  → convert to [[lat, lon]]
    const latLngs = serverCoords.map(c => [c[1], c[0]]);

    if (routeLayerReroute) {
        routeLayerReroute.setLatLngs(latLngs);
    }
    currentRouteCoords = latLngs;
    totalRouteLengthM  = calcRouteLength(latLngs);
}

function drawFloodZone() {
    if (floodZoneLayer) return;
    floodZoneLayer = L.polygon([
        [10.32, 76.32],[10.35, 76.35],[10.34, 76.38],
        [10.30, 76.40],[10.28, 76.35]
    ], {
        color: '#ff3366',
        fillColor: '#ff3366',
        fillOpacity: 0.13,
        weight: 1.5,
        dashArray: '6, 4',
    }).addTo(map).bindPopup(
        '<b style="color:#ff3366">⚠ Chalakudy Flood Basin</b><br>Cloudburst inundation zone<br><small>PI-GNN detected critical hazard</small>'
    );
    // Auto-open popup briefly
    setTimeout(() => { if (floodZoneLayer) floodZoneLayer.openPopup(); }, 500);
}

function clearFloodZone() {
    if (floodZoneLayer) { map.removeLayer(floodZoneLayer); floodZoneLayer = null; }
}

function resetMapRoute() {
    if (routeLayerReroute) { map.removeLayer(routeLayerReroute); routeLayerReroute = null; }
    clearFloodZone();
    drawOriginalRoute();
    currentRouteCoords = routeCoords.original;
    totalRouteLengthM  = calcRouteLength(currentRouteCoords);
}

// ── Truck Animation ───────────────────────────────────────────────────────────

function startTruckAnimation(useReroute = false, overrideCoords = null) {
    stopTruckAnimation();
    const coords = overrideCoords ||
                   (useReroute ? routeCoords.reroute : routeCoords.original);
    if (!coords || coords.length === 0) return;

    truckAnimIndex = 0;
    truckAnimInterval = setInterval(() => {
        if (truckAnimIndex >= coords.length) {
            stopTruckAnimation();
            return;
        }
        const pos = coords[truckAnimIndex];
        const latLng = Array.isArray(pos) ? [pos[0], pos[1]] : [pos.lat, pos.lng];
        if (truckMarker) {
            truckMarker.setLatLng(latLng);
            truckLatLng = latLng;

            // Rotate truck icon toward next point
            if (truckAnimIndex < coords.length - 1) {
                const next = coords[truckAnimIndex + 1];
                const nextLatLng = Array.isArray(next) ? next : [next.lat, next.lng];
                const bearing = calcBearing(latLng[0], latLng[1], nextLatLng[0], nextLatLng[1]);
                truckMarker.getElement() &&
                    (truckMarker.getElement().style.transform += ` rotate(${bearing}deg)`);
            }
        }
        distanceCoveredM = Math.min(
            truckAnimIndex / coords.length * totalRouteLengthM,
            totalRouteLengthM
        );
        truckAnimIndex += 2;
    }, 100);
}

function stopTruckAnimation() {
    if (truckAnimInterval) {
        clearInterval(truckAnimInterval);
        truckAnimInterval = null;
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SSE CONNECTION — Real-time backend feed
// ═══════════════════════════════════════════════════════════════════════════════

function connectSSE() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }

    eventSource = new EventSource(SSE_URL);

    eventSource.onopen = () => {
        addLog("✓ Connected to PI-GNN telemetry stream (SSE).", "success");
        els.liveIndicator.textContent = 'LIVE';
        els.liveIndicator.classList.remove('disconnected');
        els.connectionDot.style.animation = "pulse 1.5s infinite alternate";
        els.connectionDot.style.opacity   = "1";
    };

    eventSource.onerror = () => {
        addLog("⚠ SSE connection lost. Retrying in 3 s…", "alert");
        els.liveIndicator.textContent = 'OFFLINE';
        els.liveIndicator.classList.add('disconnected');
        els.connectionDot.style.animation = "none";
        els.connectionDot.style.opacity   = "0.25";
    };

    eventSource.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            handleSSEEvent(data);
        } catch (err) {
            console.error("SSE parse error:", err, e.data);
        }
    };

    return eventSource;
}

function handleSSEEvent(data) {
    switch (data.type) {
        case "STAGE_UPDATE":   handleStageUpdate(data);   break;
        case "HAZARD_UPDATE":  handleHazardUpdate(data);  break;
        case "REROUTE_UPDATE": handleRerouteUpdate(data); break;
        case "REPORT_EVENT":   handleReportEvent(data);   break;
        case "COUNTDOWN":
            addLog(data.message, 'countdown');
            break;
        case "SIM_RESTART":
            addLog("♻ Simulation loop restarting from Stage 0.", 'info');
            resetForNewLoop();
            break;
        default:
            console.log('[SSE]', data.type, data);
    }
}

// ── Stage Update ──────────────────────────────────────────────────────────────
function handleStageUpdate(data) {
    currentStage = data.stage;
    els.stageLabel.textContent = `Stage ${data.stage}: ${data.stage_label}`;
    els.stageVal.textContent   = data.stage;

    if (data.logs) {
        data.logs.forEach(msg => {
            const type = (msg.includes('CRITICAL') || msg.includes('⚠') || msg.includes('🔴'))
                         ? 'alert' : msg.includes('✅') ? 'success' : 'info';
            addLog(msg, type);
        });
    }

    // Network badge
    if (data.network_status === 'VDTN_ACTIVE') {
        els.mapNetworkBadge.textContent = 'VDTN MESH';
        els.mapNetworkBadge.classList.add('vdtn');
    } else {
        els.mapNetworkBadge.textContent = 'CELLULAR';
        els.mapNetworkBadge.classList.remove('vdtn');
    }

    // Stage-specific UI + TTS
    switch (data.stage) {
        case 0:
            speak("PI-GNN system initialized. All sensors nominal. NH544 corridor clear.", false);
            break;
        case 1:
            startTruckAnimation(false);
            speak("Fleet truck TRK seven seven four X is now en route via NH 544. All conditions nominal.", false);
            break;
        case 2:
            drawFloodZone();
            speak("Warning! Unpredicted cloudburst detected in Chalakudy Basin. Manning roughness increasing. Hazard analysis in progress.", true);
            break;
        case 3:
            speak("Critical alert! Cellular infrastructure failure at Sector 7. Switching to V D T N offline mesh network.", true);
            break;
        case 4:
            speak("Hazard coefficient exceeds critical threshold of 0.8. Flood confirmed on NH 544 corridor. Initiating reroute calculation.", true);
            break;
        case 5:
            speak("Route has been diverted. PI-GNN A-star algorithm has identified a safe corridor. Follow the green route on your navigation map.", true);
            break;
    }
}

// ── Hazard Update ─────────────────────────────────────────────────────────────
function handleHazardUpdate(data) {
    els.hazardVal.textContent  = data.hazard_coefficient.toFixed(3);
    els.affectedVal.textContent = (data.affected_segment_ids || []).length;
    els.mapHazard.textContent  = `${data.hazard_coefficient.toFixed(2)} m²/s`;

    if (data.predicted_depth    !== undefined) els.depthVal.textContent    = data.predicted_depth.toFixed(2);
    if (data.predicted_velocity !== undefined) els.velocityVal.textContent = data.predicted_velocity.toFixed(2);
    if (data.manning_n          !== undefined) els.manningVal.textContent  = data.manning_n.toFixed(3);

    updateSeverityColors(data.severity_class);

    if (data.is_critical) {
        addLog(`🔴 CRITICAL hazard at ${data.node_id}: ${data.hazard_coefficient.toFixed(2)} m²/s — ${(data.affected_segment_ids || []).length} segments affected`, "alert");
    }
}

// ── Reroute Update ────────────────────────────────────────────────────────────
function handleRerouteUpdate(data) {
    const lenKm  = (data.length_m / 1000).toFixed(1);
    totalRouteLengthM = data.length_m;

    if (data.is_rerouted && !isRerouted) {
        // ── Route just changed: original → rerouted ──────────────────────────
        isRerouted = true;

        els.mapRouteBadge.textContent = 'DIVERTED (A*)';
        els.mapRouteBadge.classList.add('rerouted');
        els.rerouteAlert.classList.add('active');
        els.alertDetail.textContent = `Safe corridor: ${lenKm} km via PI-GNN A* routing`;

        addLog(`🔀 Route DIVERTED! New path: ${lenKm} km — PI-GNN A* safe corridor.`, "reroute");

        // Draw reroute using server-provided coordinates
        drawRerouteRoute(data.coordinates && data.coordinates.length > 0 ? data.coordinates : null);

        // TTS: announce route change with full details
        const etaMin = Math.round(data.length_m / ((AVG_SPEED_KMH * 1000) / 3600) / 60);
        speak(
            `Attention driver! Your route has been changed due to a critical flood hazard detected by PI-GNN. ` +
            `New route distance is ${lenKm} kilometers. Estimated arrival in ${etaMin} minutes. ` +
            `Follow the green corridor shown on your navigation map. Drive safely.`,
            true
        );

    } else if (!data.is_rerouted && isRerouted) {
        // ── Route restored to original ────────────────────────────────────────
        isRerouted = false;
        els.mapRouteBadge.textContent = 'ORIGINAL ROUTE';
        els.mapRouteBadge.classList.remove('rerouted');
        els.rerouteAlert.classList.remove('active');
        addLog(`✅ Route restored to original NH544 corridor. Distance: ${lenKm} km.`, "success");
        resetMapRoute();
        speak(`Route restored to original NH544 corridor. Distance ${lenKm} kilometers.`);

    } else if (data.is_rerouted && data.coordinates && data.coordinates.length > 0) {
        // ── Live update of rerouted path coordinates ──────────────────────────
        updateRerouteFromCoords(data.coordinates);
    }

    // Update distance display
    els.mapDistance.textContent = `${lenKm} km`;
    updateEta(data.length_m);
    updateNavPanel();
}

// ── Report Event (from another vehicle/source via SSE) ────────────────────────
function handleReportEvent(data) {
    const r         = data.report;
    const typeLabel = r.type.replace(/_/g, ' ').toUpperCase();
    addLog(`📋 [REPORT] ${r.vehicle_id}: ${typeLabel} (severity ${r.severity}/4) — ${r.description || 'No details'}`, 'report');

    if (r.lat && r.lon) {
        const reportIcon = L.divIcon({
            className: '',
            html: `<div style="font-size:18px;filter:drop-shadow(0 0 5px rgba(255,170,0,0.9));cursor:pointer;">${getReportEmoji(r.type)}</div>`,
            iconSize: [22, 22], iconAnchor: [11, 11],
        });
        const marker = L.marker([r.lat, r.lon], { icon: reportIcon })
            .addTo(map)
            .bindPopup(
                `<b style="color:#ffaa00">${typeLabel}</b><br>` +
                `Severity: <b>${r.severity}/4</b><br>` +
                `${r.description ? r.description + '<br>' : ''}` +
                `Reported by: ${r.vehicle_id}<br>` +
                `<small>${new Date(r.timestamp).toLocaleTimeString()}</small>`
            );
        reportMarkers.push(marker);
    }
}

function getReportEmoji(type) {
    const emojis = {
        flood: '🌊', landslide: '⛰️', traffic_congestion: '🚗',
        accident: '💥', road_blocked: '🚧', hazard: '⚡'
    };
    return emojis[type] || '📍';
}

// ── Reset for new simulation loop ─────────────────────────────────────────────
function resetForNewLoop() {
    isRerouted   = false;
    currentStage = -1;

    stopTruckAnimation();
    resetMapRoute();

    els.mapRouteBadge.textContent   = 'ORIGINAL ROUTE';
    els.mapRouteBadge.classList.remove('rerouted');
    els.mapNetworkBadge.textContent = 'CELLULAR';
    els.mapNetworkBadge.classList.remove('vdtn');
    els.rerouteAlert.classList.remove('active');

    els.mapDistance.textContent = '29.4 km';
    els.mapEta.textContent      = '44 min';
    els.mapHazard.textContent   = '0.11 m²/s';
    els.stageLabel.textContent  = 'Stage 0: Initializing…';
    els.stageVal.textContent    = '0';
    els.hazardVal.textContent   = '0.111';
    els.depthVal.textContent    = '0.20';
    els.velocityVal.textContent = '0.50';
    els.manningVal.textContent  = '0.015';
    els.affectedVal.textContent = '0';

    if (els.navDistance)    els.navDistance.textContent = '29.4 km';
    if (els.navEta)         els.navEta.textContent      = '44 min';
    if (els.navProgress)    els.navProgress.textContent = '0%';
    if (els.navProgressBar) els.navProgressBar.style.width = '0%';
    if (els.navRouteStatus) {
        els.navRouteStatus.textContent = 'ON ROUTE';
        els.navRouteStatus.className = 'nav-route-status on-route';
    }

    updateSeverityColors('SAFE');
    distanceCoveredM = 0;
    totalRouteLengthM = 29390.3;
    currentRouteCoords = routeCoords.original;

    if (truckMarker) truckMarker.setLatLng([10.249946, 76.319778]);

    reportMarkers.forEach(m => map.removeLayer(m));
    reportMarkers = [];
}

// ═══════════════════════════════════════════════════════════════════════════════
// USER EVENT REPORTING
// ═══════════════════════════════════════════════════════════════════════════════

window.openReportModal = function(type) {
    reportType     = type;
    reportSeverity = 1;
    document.getElementById('report-modal').classList.add('active');

    const labels = {
        flood:             '🌊 Report Flood',
        landslide:         '⛰️ Report Landslide',
        traffic_congestion:'🚗 Report Traffic Congestion',
        accident:          '💥 Report Accident',
        road_blocked:      '🚧 Report Road Block',
        hazard:            '⚡ Report Other Hazard',
    };
    document.getElementById('modal-title').textContent = labels[type] || 'Report Event';
    document.getElementById('report-description').value = '';

    document.querySelectorAll('.sev-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('sev-1').classList.add('active');

    const pos = truckMarker ? truckMarker.getLatLng() : { lat: 10.31, lng: 76.37 };
    document.getElementById('report-location').textContent =
        `GPS: ${pos.lat.toFixed(6)}°N, ${pos.lng.toFixed(6)}°E`;
};

window.closeReportModal = function() {
    document.getElementById('report-modal').classList.remove('active');
};

window.setSeverity = function(sev) {
    reportSeverity = sev;
    document.querySelectorAll('.sev-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`sev-${sev}`).classList.add('active');
};

window.submitReport = async function() {
    const description = document.getElementById('report-description').value.trim();
    const pos = truckMarker ? truckMarker.getLatLng() : { lat: 10.31, lng: 76.37 };

    const report = {
        type:        reportType,
        severity:    reportSeverity,
        lat:         pos.lat,
        lon:         pos.lng,
        description: description,
        vehicle_id:  'TRK-774-X',
    };

    closeReportModal();

    const typeLabel = reportType.replace(/_/g, ' ');
    addLog(`📤 Submitting ${typeLabel} report (severity ${reportSeverity}/4)…`, 'report');

    try {
        const res  = await fetch(`${SERVER_URL}/report`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(report),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        addLog(`✅ Report #${data.report_id} accepted — broadcast to VDTN mesh.`, 'success');
        speak(`${typeLabel} report submitted successfully. Report ID ${data.report_id}.`);

    } catch (e) {
        addLog(`⚠ Report upload failed (${e.message}). Saved locally.`, 'alert');

        // Local fallback: show marker on map even if server is unreachable
        const icon = L.divIcon({
            className: '',
            html: `<div style="font-size:18px;filter:drop-shadow(0 0 5px rgba(255,170,0,0.9));">${getReportEmoji(reportType)}</div>`,
            iconSize: [22, 22], iconAnchor: [11, 11],
        });
        const marker = L.marker([pos.lat, pos.lng], { icon })
            .addTo(map)
            .bindPopup(
                `<b style="color:#ffaa00">${typeLabel.toUpperCase()}</b><br>` +
                `Severity: ${reportSeverity}/4<br>` +
                `${description || 'No details'}<br>` +
                `<small>📍 Local report (offline)</small>`
            );
        marker.openPopup();
        reportMarkers.push(marker);
        speak(`${typeLabel} report saved locally. Will sync when connection is restored.`);
    }
};

// ═══════════════════════════════════════════════════════════════════════════════
// V2V FLEET SIMULATION
// ═══════════════════════════════════════════════════════════════════════════════

const v2vFleet = [
    { id: 'TRK-102-Y', dist: 1.2, status: 'NOMINAL' },
    { id: 'TRK-881-A', dist: 3.4, status: 'NOMINAL' },
    { id: 'VAN-44X',   dist: 5.1, status: 'NOMINAL' },
    { id: 'FMCG-02',   dist: 7.8, status: 'NOMINAL' },
];

function renderV2V() {
    els.v2vList.innerHTML = '';
    v2vFleet.forEach(v => {
        v.dist += (Math.random() - 0.5) * 0.12;
        if (v.dist < 0.1) v.dist = 0.1;

        if (currentSeverity === 'CRITICAL' && Math.random() > 0.72) {
            v.status = 'ALERT';
        } else if (currentSeverity === 'SAFE') {
            v.status = 'NOMINAL';
        }

        const li = document.createElement('li');
        li.className = 'v2v-item';
        const statusColor = v.status === 'ALERT' ? 'var(--color-critical)' : 'var(--color-safe)';
        const statusDot   = v.status === 'ALERT' ? '🔴' : '🟢';
        li.innerHTML =
            `<span style="color:${statusColor}">${statusDot} ${v.id}</span>` +
            `<span class="v2v-dist">${v.dist.toFixed(1)} km</span>`;
        els.v2vList.appendChild(li);
    });
}
setInterval(renderV2V, 2500);
renderV2V();

// ═══════════════════════════════════════════════════════════════════════════════
// SIMULATION RESTART
// ═══════════════════════════════════════════════════════════════════════════════

els.btnSimRestart.addEventListener('click', async () => {
    addLog("↺ Requesting simulation restart…", "info");
    try {
        const res = await fetch(`${SERVER_URL}/start_sim`, { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        addLog("✓ Simulation restart triggered.", "success");
        resetForNewLoop();
    } catch (e) {
        addLog(`Restart failed: ${e.message}`, "alert");
        // Still reset UI even if server unreachable
        resetForNewLoop();
    }
});

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION PANEL UPDATE LOOP
// ═══════════════════════════════════════════════════════════════════════════════

navUpdateInterval = setInterval(updateNavPanel, 1500);

// ═══════════════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════════════════════

// Initialize Leaflet map
initMap();

// Connect to SSE stream
connectSSE();

// Register Service Worker (PWA support)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('./service-worker.js')
            .then(reg  => console.log('[SW] Registered:', reg.scope))
            .catch(err => console.log('[SW] Registration failed:', err));
    });
}

addLog("🚀 HUD initialized. Connecting to PI-GNN backend…", "info");
