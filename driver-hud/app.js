const SERVER_URL = "http://localhost:8080/stream";
const SET_ROUTE_URL = "http://localhost:8080/set_route";

const els = {
    overallStatus: document.getElementById('overall-status'),
    routeType: document.getElementById('route-type'),
    routeLength: document.getElementById('route-length'),
    routeEta: document.getElementById('route-eta'),
    rerouteAlert: document.getElementById('reroute-alert'),
    hazardVal: document.getElementById('hazard-val'),
    affectedVal: document.getElementById('affected-val'),
    eventFeed: document.getElementById('event-feed'),
    connectionDot: document.getElementById('connection-dot'),
    btnRecalculate: document.getElementById('btn-recalculate'),
    routeOrigin: document.getElementById('route-origin'),
    routeDest: document.getElementById('route-dest'),
    routeWaypoint: document.getElementById('route-waypoint'),
    v2vList: document.getElementById('v2v-list'),
    reportList: document.getElementById('report-list'),
    envFlood: document.getElementById('env-flood'),
    envTraffic: document.getElementById('env-traffic'),
    envWeather: document.getElementById('env-weather'),
    envBlocks: document.getElementById('env-blocks'),
    envLandslide: document.getElementById('env-landslide')
};

function getTimeStr() {
    return new Date().toLocaleTimeString([], { hour12: false });
}

function addLog(msg, type = 'safe') {
    const li = document.createElement('li');
    li.className = type;
    li.innerHTML = `<span class="time">[${getTimeStr()}]</span> ${msg}`;
    els.eventFeed.prepend(li);
    if(els.eventFeed.children.length > 50) els.eventFeed.lastChild.remove();
}

function updateColors(severity) {
    els.overallStatus.className = 'status-badge ' + severity.toLowerCase();
    els.overallStatus.textContent = severity;
    
    let colorVar = 'var(--color-safe)';
    if(severity === 'WARNING') colorVar = 'var(--color-warning)';
    if(severity === 'CRITICAL') colorVar = 'var(--color-critical)';
    
    els.hazardVal.style.color = colorVar;
    els.connectionDot.style.background = colorVar;
    els.connectionDot.style.boxShadow = `0 0 10px ${colorVar}`;
    
    // Update Environmental Conditions Dynamically
    if(severity === 'CRITICAL') {
        els.envFlood.textContent = 'HIGH';
        els.envFlood.parentElement.className = 'env-item critical';
        els.envTraffic.textContent = 'Gridlock';
        els.envTraffic.parentElement.className = 'env-item critical';
        els.envWeather.textContent = 'Cloudburst / Heavy Rain';
        els.envWeather.parentElement.className = 'env-item critical';
        els.envBlocks.textContent = 'Debris Detected';
        els.envBlocks.parentElement.className = 'env-item critical';
        els.envLandslide.textContent = 'High Risk';
        els.envLandslide.parentElement.className = 'env-item critical';
    } else if(severity === 'WARNING') {
        els.envFlood.textContent = 'Elevated';
        els.envFlood.parentElement.className = 'env-item warning';
        els.envTraffic.textContent = 'Congested';
        els.envTraffic.parentElement.className = 'env-item warning';
        els.envWeather.textContent = 'Moderate Rain';
        els.envWeather.parentElement.className = 'env-item warning';
        els.envBlocks.textContent = 'Possible';
        els.envBlocks.parentElement.className = 'env-item warning';
        els.envLandslide.textContent = 'Moderate Risk';
        els.envLandslide.parentElement.className = 'env-item warning';
    } else {
        els.envFlood.textContent = 'Low';
        els.envFlood.parentElement.className = 'env-item';
        els.envTraffic.textContent = 'Smooth';
        els.envTraffic.parentElement.className = 'env-item';
        els.envWeather.textContent = 'Clear';
        els.envWeather.parentElement.className = 'env-item';
        els.envBlocks.textContent = 'None';
        els.envBlocks.parentElement.className = 'env-item';
        els.envLandslide.textContent = 'No Risk';
        els.envLandslide.parentElement.className = 'env-item';
    }
}

// Routing Logic
els.btnRecalculate.addEventListener('click', async () => {
    addLog("Requesting route calculation...", "safe");
    const origin = els.routeOrigin.value.split(',').map(Number);
    const dest = els.routeDest.value.split(',').map(Number);
    const waypoint = els.routeWaypoint.value;
    
    if (waypoint) {
        addLog(`Fixing route via waypoint: ${els.routeWaypoint.options[els.routeWaypoint.selectedIndex].text}`, "safe");
    }

    try {
        const res = await fetch(SET_ROUTE_URL, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ origin, destination: dest }) // backend handles a single set of endpoints for now
        });
        const data = await res.json();
        if(data.found) {
            addLog(`Route successfully updated. Length: ${(data.length_m/1000).toFixed(1)} km`, "safe");
            updateEta(data.length_m);
        } else {
            addLog("No route found between endpoints!", "critical");
        }
    } catch(e) {
        addLog("Routing request failed: " + e.message, "critical");
    }
});

function updateEta(lengthMeters) {
    // Assume average speed 40 km/h (11.11 m/s)
    const speedMps = 11.11;
    const seconds = lengthMeters / speedMps;
    const minutes = Math.round(seconds / 60);
    els.routeEta.textContent = minutes;
}

// User Reports
window.submitReport = function(type) {
    addLog(`Submitted ${type} report to VDTN mesh.`, "warning");
    const li = document.createElement('li');
    li.innerHTML = `<span class="time">[${getTimeStr()}]</span> YOU reported a ${type}.`;
    els.reportList.prepend(li);
    
    // Simulate sending to backend (could add fetch here)
};

// Simulate incoming reports from other drivers
setTimeout(() => {
    const li = document.createElement('li');
    li.innerHTML = `<span class="time">[${getTimeStr()}]</span> VAN-44X reported heavy rain.`;
    els.reportList.prepend(li);
    addLog("Received incoming VDTN report: heavy rain", "safe");
}, 15000);

// V2V Fleet Simulation
const v2vFleet = [
    { id: 'TRK-102-Y', dist: 1.2 },
    { id: 'TRK-881-A', dist: 3.4 },
    { id: 'VAN-44X', dist: 5.1 }
];
function renderV2V() {
    els.v2vList.innerHTML = '';
    v2vFleet.forEach(v => {
        // jitter distance
        v.dist += (Math.random() - 0.5) * 0.1;
        if(v.dist < 0.1) v.dist = 0.1;
        const li = document.createElement('li');
        li.className = 'v2v-item';
        li.innerHTML = `<span>${v.id}</span> <span class="v2v-dist">${v.dist.toFixed(2)} km</span>`;
        els.v2vList.appendChild(li);
    });
}
setInterval(renderV2V, 2000);
renderV2V();

// SSE Connection
function connectSSE() {
    const eventSource = new EventSource(SERVER_URL);

    eventSource.onopen = () => {
        addLog("Connected to VDTN telemetry stream.", "safe");
        els.connectionDot.style.animation = "pulse 1.5s infinite alternate";
    };

    eventSource.onerror = () => {
        addLog("Connection lost. Retrying...", "critical");
        els.connectionDot.style.animation = "none";
        els.connectionDot.style.opacity = "0.2";
    };

    eventSource.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            
            if (data.type === "HAZARD_UPDATE") {
                els.hazardVal.textContent = data.hazard_coefficient.toFixed(3);
                els.affectedVal.textContent = data.affected_segment_ids.length;
                updateColors(data.severity_class);
                
                if (data.is_critical) {
                    addLog(`CRITICAL hazard at ${data.node_id} (h=${data.hazard_coefficient.toFixed(2)})`, "critical");
                }
            } 
            else if (data.type === "REROUTE_UPDATE") {
                const lenKm = (data.length_m / 1000).toFixed(1);
                els.routeLength.textContent = lenKm;
                updateEta(data.length_m);
                
                if (data.is_rerouted) {
                    els.routeType.textContent = "DIVERTED (A*)";
                    els.routeType.style.color = "var(--color-reroute)";
                    els.rerouteAlert.classList.add("active");
                    addLog(`Route diverted! New length: ${lenKm} km`, "reroute");
                } else {
                    els.routeType.textContent = "ORIGINAL";
                    els.routeType.style.color = "#fff";
                    els.rerouteAlert.classList.remove("active");
                    addLog("Route nominal. Tracking original path.");
                }
            }
        } catch(err) {
            console.error("Parse error:", err);
        }
    };
}

connectSSE();

// Register PWA Service Worker for Offline Mode
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('./service-worker.js')
            .then(reg => console.log('ServiceWorker registered:', reg.scope))
            .catch(err => console.log('ServiceWorker registration failed:', err));
    });
}
