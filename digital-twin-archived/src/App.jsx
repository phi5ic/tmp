import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Bell, CheckCircle2, CircleDot, LocateFixed, MapPin, Radio, Send, Volume2, Waves } from 'lucide-react'
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import routes from './routes.json'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8080'
const DEFAULT_ORIGIN = [10.249946, 76.319778]
const DEFAULT_DESTINATION = [10.379903, 76.390489]
const KERALA_CENTER = [10.36, 76.26]
const LOCATIONS = {
  'Chalakudy, Kerala': [10.303956, 76.335678],
  'Angamaly, Kerala': [10.196, 76.387],
  'Aluva, Kerala': [10.107, 76.351],
  'Kochi, Kerala': [9.9312, 76.2673],
  'Palakkad, Kerala': [10.7867, 76.6548],
}

const markerIcon = (color) => L.divIcon({
  className: 'custom-marker',
  html: `<span style="--marker-color:${color}"></span>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
})

const startIcon = markerIcon('#16a34a')
const destinationIcon = markerIcon('#2563eb')
const hazardIcon = markerIcon('#dc2626')
const reportIcon = markerIcon('#f59e0b')

function MapViewport({ route }) {
  const map = useMap()
  useEffect(() => {
    if (route.length > 1) map.fitBounds(route, { padding: [28, 28] })
  }, [map, route])
  return null
}

function toLeafletCoordinates(geojson) {
  const coordinates = geojson?.features?.flatMap((feature) => feature.geometry?.coordinates || []) || []
  return coordinates.map(([longitude, latitude]) => [latitude, longitude])
}

function formatDistance(meters) {
  return `${(meters / 1000).toFixed(1)} km`
}

function App() {
  const [from, setFrom] = useState('Palakkad, Kerala')
  const [to, setTo] = useState('Kochi, Kerala')
  const [route, setRoute] = useState(routes.original.map(([latitude, longitude]) => [latitude, longitude]))
  const [routeInfo, setRouteInfo] = useState({ distance: 42.8, eta: 68, rerouted: false })
  const [hazards, setHazards] = useState([])
  const [reports, setReports] = useState([])
  const [latestHazard, setLatestHazard] = useState(null)
  const [connection, setConnection] = useState('connecting')
  const [routeError, setRouteError] = useState('')
  const [report, setReport] = useState({ type: 'Flood', location: 'Chalakudy, Kerala', description: '' })
  const [reportMessage, setReportMessage] = useState('')

  const announce = useCallback((message) => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(message))
    }
  }, [])

  const applyRouteUpdate = useCallback((data) => {
    const updatedRoute = toLeafletCoordinates(data.geojson)
    if (updatedRoute.length > 1) setRoute(updatedRoute)
    if (data.length_m) {
      const distance = data.length_m / 1000
      setRouteInfo({ distance, eta: Math.max(1, Math.round((distance / 38) * 60)), rerouted: Boolean(data.is_rerouted) })
    }
    if (data.is_rerouted) announce('Route changed. A safer route has been selected because a hazard was detected ahead.')
  }, [announce])

  useEffect(() => {
    const stream = new EventSource(`${BACKEND_URL}/stream`)
    stream.onopen = () => setConnection('live')
    stream.onerror = () => setConnection('offline')
    stream.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'HAZARD_UPDATE') {
        setLatestHazard(data)
        setHazards((current) => [{ ...data, receivedAt: new Date().toLocaleTimeString() }, ...current].slice(0, 8))
      }
      if (data.type === 'REROUTE_UPDATE') applyRouteUpdate(data)
      if (data.type === 'USER_REPORT') {
        const location = LOCATIONS[data.location] || LOCATIONS['Chalakudy, Kerala']
        setReports((current) => {
          const alreadyVisible = current.some((item) =>
            item.location === data.location &&
            item.description === data.description &&
            item.type === (data.event_type || data.type),
          )
          return alreadyVisible
            ? current
            : [{ ...data, type: data.event_type || data.type, coordinates: location }, ...current].slice(0, 12)
        })
      }
    }
    return () => stream.close()
  }, [applyRouteUpdate])

  const calculateRoute = async () => {
    setRouteError('')
    const origin = LOCATIONS[from] || DEFAULT_ORIGIN
    const destination = LOCATIONS[to] || DEFAULT_DESTINATION
    try {
      const response = await fetch(`${BACKEND_URL}/set_route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ origin: [origin[1], origin[0]], destination: [destination[1], destination[0]] }),
      })
      if (!response.ok) throw new Error('Route service unavailable')
      const data = await response.json()
      if (!data.found) throw new Error('No route found')
      applyRouteUpdate(data)
    } catch (error) {
      setRouteError(error.message)
      const fallback = routes.original.map(([latitude, longitude]) => [latitude, longitude])
      setRoute(fallback)
    }
  }

  const submitReport = async (event) => {
    event.preventDefault()
    if (!report.description.trim()) return
    const coordinates = LOCATIONS[report.location]
    const localReport = { ...report, coordinates, receivedAt: new Date().toLocaleTimeString(), source: 'You' }
    setReports((current) => [localReport, ...current])
    setReportMessage('Report shared with the live hazard stream.')
    setReport((current) => ({ ...current, description: '' }))
    try {
      await fetch(`${BACKEND_URL}/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...report, coordinates: [coordinates[1], coordinates[0]] }),
      })
    } catch {
      setReportMessage('Saved locally. Backend is currently offline.')
    }
  }

  const displayHazards = useMemo(() => {
    const live = latestHazard ? [{
      coordinates: latestHazard.node_id?.includes('B') ? LOCATIONS['Chalakudy, Kerala'] : DEFAULT_ORIGIN,
      title: latestHazard.severity_class || 'Hazard',
      detail: `${latestHazard.hazard_coefficient?.toFixed?.(2) || latestHazard.hazard_coefficient} m²/s`,
    }] : []
    return live
  }, [latestHazard])

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Waves size={21} /></div>
          <div><strong>RouteSuraksha</strong><span>KERALA</span></div>
        </div>
        <div className="live-state"><span className={`live-dot ${connection}`} /> {connection === 'live' ? 'QGIS SIMULATION LIVE' : 'BACKEND OFFLINE'}</div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">REAL-TIME ROAD SAFETY</p>
          <h1>Know the road.<br /><em>Choose the safer way.</em></h1>
          <p className="hero-copy">Live flood intelligence from the Kerala digital twin, combined with safe navigation and community reports.</p>
        </div>
        <div className="hero-status"><Radio size={17} /><span><b>{hazards.length}</b> events received</span></div>
      </section>

      <section className="dashboard-grid">
        <aside className="side-panel">
          <div className="card route-card">
            <div className="card-heading"><div><p className="eyebrow">NAVIGATION</p><h2>Plan your journey</h2></div><LocateFixed size={19} /></div>
            <label>From<select value={from} onChange={(event) => setFrom(event.target.value)}>{Object.keys(LOCATIONS).map((location) => <option key={location}>{location}</option>)}</select></label>
            <label>To<select value={to} onChange={(event) => setTo(event.target.value)}>{Object.keys(LOCATIONS).map((location) => <option key={location}>{location}</option>)}</select></label>
            <button className="primary-button" onClick={calculateRoute}><CircleDot size={17} /> Calculate safe route</button>
            {routeError && <p className="error-text">{routeError}. Showing the QGIS demo route.</p>}
          </div>

          <div className="metrics-row">
            <div className="metric-card"><span>Distance</span><strong>{routeInfo.distance.toFixed(1)} <small>km</small></strong></div>
            <div className="metric-card"><span>Estimated time</span><strong>{routeInfo.eta} <small>min</small></strong></div>
          </div>

          <div className={`card alert-card ${latestHazard?.is_critical ? 'critical' : ''}`}>
            <div className="alert-title"><AlertTriangle size={18} /><span>{latestHazard?.is_critical ? 'Critical hazard detected' : 'Route safety monitor'}</span></div>
            <p>{latestHazard ? `${latestHazard.node_id} reports ${latestHazard.severity_class.toLowerCase()} conditions (${latestHazard.hazard_coefficient.toFixed(2)} m²/s).` : 'Waiting for live QGIS and PI-GNN telemetry.'}</p>
            <button className="link-button" onClick={() => latestHazard && announce('Live hazard alert. Please review your route.') }><Volume2 size={15} /> Read alert aloud</button>
          </div>

          <form className="card report-card" onSubmit={submitReport}>
            <div className="card-heading"><div><p className="eyebrow">COMMUNITY SIGNAL</p><h2>Report an event</h2></div><MapPin size={19} /></div>
            <label>Event type<select value={report.type} onChange={(event) => setReport({ ...report, type: event.target.value })}><option>Flood</option><option>Landslide</option><option>Traffic congestion</option><option>Accident</option><option>Road blocked</option></select></label>
            <label>Location<select value={report.location} onChange={(event) => setReport({ ...report, location: event.target.value })}>{Object.keys(LOCATIONS).map((location) => <option key={location}>{location}</option>)}</select></label>
            <label>What did you see?<textarea value={report.description} onChange={(event) => setReport({ ...report, description: event.target.value })} placeholder="Add a short description..." required /></label>
            <button className="secondary-button" type="submit"><Send size={16} /> Share report</button>
            {reportMessage && <p className="success-text"><CheckCircle2 size={15} /> {reportMessage}</p>}
          </form>
        </aside>

        <section className="map-card">
          <div className="map-toolbar"><span><span className="legend-line" /> {routeInfo.rerouted ? 'Safer alternative route' : 'Current route'}</span><span className="map-note"><span className="legend-dot danger" /> Live hazards <span className="legend-dot report" /> Reports</span></div>
          <MapContainer center={KERALA_CENTER} zoom={10} scrollWheelZoom className="leaflet-map">
            <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            <MapViewport route={route} />
            <Polyline positions={route} pathOptions={{ color: routeInfo.rerouted ? '#15803d' : '#0f766e', weight: 5, opacity: 0.9 }} />
            <Marker position={route[0] || DEFAULT_ORIGIN} icon={startIcon}><Popup>Start: {from}</Popup></Marker>
            <Marker position={route[route.length - 1] || DEFAULT_DESTINATION} icon={destinationIcon}><Popup>Destination: {to}</Popup></Marker>
            {displayHazards.map((hazard, index) => <Marker key={`hazard-${index}`} position={hazard.coordinates} icon={hazardIcon}><Popup><b>{hazard.title}</b><br />{hazard.detail}</Popup></Marker>)}
            {reports.map((item, index) => <Marker key={`report-${index}`} position={item.coordinates} icon={reportIcon}><Popup><b>{item.type}</b><br />{item.location}<br />{item.description}</Popup></Marker>)}
            {latestHazard && <CircleMarker center={displayHazards[0].coordinates} radius={26} pathOptions={{ color: '#dc2626', fillColor: '#dc2626', fillOpacity: 0.12, weight: 2 }} />}
          </MapContainer>
          <div className="map-footer"><span><span className="legend-dot start" /> Start</span><span><span className="legend-dot destination" /> Destination</span><span><span className="legend-dot danger" /> Hazard</span><span><span className="legend-dot report" /> Community report</span></div>
        </section>
      </section>

      <section className="activity-strip">
        <div className="activity-header"><div><p className="eyebrow">LIVE ACTIVITY</p><h2>Safety feed</h2></div><Bell size={19} /></div>
        <div className="activity-list">
          {hazards.slice(0, 3).map((item, index) => <div className="activity-item" key={`hazard-feed-${index}`}><span className="activity-icon danger"><AlertTriangle size={15} /></span><div><b>{item.severity_class} hazard · {item.node_id}</b><p>Coefficient {item.hazard_coefficient.toFixed(2)} m²/s · {item.receivedAt}</p></div></div>)}
          {reports.slice(0, 3).map((item, index) => <div className="activity-item" key={`report-feed-${index}`}><span className="activity-icon report"><MapPin size={15} /></span><div><b>{item.type} reported · {item.location}</b><p>{item.description} · {item.receivedAt}</p></div></div>)}
          {!hazards.length && !reports.length && <p className="empty-feed">Live hazard and community events will appear here.</p>}
        </div>
      </section>
    </main>
  )
}

export default App
