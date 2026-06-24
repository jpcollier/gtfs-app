import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import * as d3 from 'd3';
import './styles.css';

const DAY_SECONDS = 24 * 60 * 60;
const SIM_START = 5 * 60 * 60;
const SIM_END = 25 * 60 * 60;
const SPEED = 240; // one real second equals four simulated minutes

function formatTime(seconds) {
  const wrapped = ((Math.floor(seconds) % DAY_SECONDS) + DAY_SECONDS) % DAY_SECONDS;
  const h = String(Math.floor(wrapped / 3600)).padStart(2, '0');
  const m = String(Math.floor((wrapped % 3600) / 60)).padStart(2, '0');
  return `${h}:${m}`;
}

function interpolateTrip(trip, seconds) {
  const samples = trip.samples;
  if (!samples || samples.length < 2 || seconds < samples[0][0] || seconds > samples[samples.length - 1][0]) return null;
  let lo = 0;
  let hi = samples.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (samples[mid][0] <= seconds) lo = mid;
    else hi = mid;
  }
  const a = samples[lo];
  const b = samples[hi];
  const t = b[0] === a[0] ? 0 : (seconds - a[0]) / (b[0] - a[0]);
  return [a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

function useSimulationClock() {
  const [seconds, setSeconds] = useState(SIM_START);
  useEffect(() => {
    let frame;
    let last = performance.now();
    const tick = (now) => {
      const delta = ((now - last) / 1000) * SPEED;
      last = now;
      setSeconds((s) => (s + delta > SIM_END ? SIM_START : s + delta));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);
  return seconds;
}

function AgencyPanel({ agency, seconds }) {
  const width = 420;
  const height = 300;
  const pad = 18;
  const projection = useMemo(() => {
    const b = agency.bounds;
    const x = d3.scaleLinear().domain([b.min_lon, b.max_lon]).range([pad, width - pad]);
    const y = d3.scaleLinear().domain([b.min_lat, b.max_lat]).range([height - pad, pad]);
    return ([lon, lat]) => [x(lon), y(lat)];
  }, [agency]);

  const line = useMemo(() => d3.line().x((d) => projection(d)[0]).y((d) => projection(d)[1]), [projection]);
  const vehicles = useMemo(() => agency.trips.map((trip) => {
    const xy = interpolateTrip(trip, seconds);
    return xy ? { id: trip.id, xy: projection(xy) } : null;
  }).filter(Boolean), [agency, seconds, projection]);

  return <article className="panel">
    <header>
      <div>
        <h2>{agency.city}</h2>
        <p>{agency.name}</p>
      </div>
      <time>{formatTime(seconds)}</time>
    </header>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Scheduled transit service for ${agency.city}`}>
      <g className="routes">
        {agency.shapes.slice(0, 900).map((shape) => <path key={shape.id} d={line(shape.points)} />)}
      </g>
      <g className="vehicles">
        {vehicles.map((v) => <circle key={v.id} cx={v.xy[0]} cy={v.xy[1]} r="2.2" />)}
      </g>
    </svg>
    <footer>{vehicles.length.toLocaleString()} active scheduled trips · {agency.service_date}</footer>
  </article>;
}

function App() {
  const [agencies, setAgencies] = useState([]);
  const [error, setError] = useState(null);
  const seconds = useSimulationClock();

  useEffect(() => {
    async function load() {
      try {
        const manifest = await fetch('/data/manifest.json').then((r) => r.json());
        const loaded = await Promise.all(manifest.agencies.map((a) => fetch(`/${a.file}`).then((r) => r.json())));
        setAgencies(loaded);
      } catch (err) {
        setError(err.message);
      }
    }
    load();
  }, []);

  return <main>
    <section className="intro">
      <p className="eyebrow">GTFS schedule animation</p>
      <h1>One representative weekday of transit service</h1>
      <p>No basemap: just scheduled vehicles moving over static route geometry in small multiples.</p>
    </section>
    {error && <p className="error">Could not load processed data: {error}</p>}
    {!error && agencies.length === 0 && <p className="loading">Loading sample agencies…</p>}
    <section className="grid">
      {agencies.map((agency) => <AgencyPanel key={agency.id} agency={agency} seconds={seconds} />)}
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
