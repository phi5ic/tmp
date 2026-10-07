const SERVER_URL = "http://localhost:8080/stream";

const els = {
    overallStatus: document.getElementById('overall-status'),
    routeType: document.getElementById('route-type'),
    routeLength: document.getElementById('route-length'),
    rerouteAlert: document.getElementById('reroute-alert'),
    hazardVal: document.getElementById('hazard-val'),
    affectedVal: document.getElementById('affected-val'),
    eventFeed: document.getElementById('event-feed'),
    connectionDot: document.getElementById('connection-dot')
};

function addLog(msg, type = 'safe') {
    const li = document.createElement('li');
    li.className = type;
    const time = new Date().toLocaleTimeString([], { hour12: false });
    li.innerHTML = `<span class="time">[${time}]</span> ${msg}`;
    els.eventFeed.prepend(li);
    if(els.eventFeed.children.length > 50) {
        els.eventFeed.lastChild.remove();
    }
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
}

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
