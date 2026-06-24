import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import * as d3 from 'd3';
import './styles.css';

const DAY_SECONDS = 24 * 60 * 60;
const SIM_START = 5 * 60 * 60;
const SIM_END = 25 * 60 * 60;
const SPEED = 240; // one real second equals four simulated minutes
const MAP_WIDTH = 720;
const MAP_HEIGHT = 520;
const MAP_PAD = 22;

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

function mergeBounds(bounds) {
  return {
    min_lon: Math.min(...bounds.map((b) => b.min_lon)),
    min_lat: Math.min(...bounds.map((b) => b.min_lat)),
    max_lon: Math.max(...bounds.map((b) => b.max_lon)),
    max_lat: Math.max(...bounds.map((b) => b.max_lat)),
  };
}

function groupAgenciesByCity(agencies) {
  const groups = d3.group(agencies, (agency) => agency.city);
  return Array.from(groups, ([city, cityAgencies]) => ({
    id: city.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    city,
    agencies: cityAgencies,
    bounds: mergeBounds(cityAgencies.map((agency) => agency.bounds)),
    serviceDates: Array.from(new Set(cityAgencies.map((agency) => agency.service_date))).sort(),
    shapes: cityAgencies.flatMap((agency) => agency.shapes.map((shape) => ({ ...shape, agencyId: agency.id }))),
    trips: cityAgencies.flatMap((agency) => agency.trips.map((trip) => ({ ...trip, agencyId: agency.id }))),
  })).sort((a, b) => a.city.localeCompare(b.city));
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

function CityMap({ city, seconds }) {
  const projection = useMemo(() => {
    const b = city.bounds;
    const lonSpan = Math.max(0.001, b.max_lon - b.min_lon);
    const latSpan = Math.max(0.001, b.max_lat - b.min_lat);
    const scale = Math.min((MAP_WIDTH - MAP_PAD * 2) / lonSpan, (MAP_HEIGHT - MAP_PAD * 2) / latSpan);
    const xOffset = (MAP_WIDTH - lonSpan * scale) / 2;
    const yOffset = (MAP_HEIGHT - latSpan * scale) / 2;
    return ([lon, lat]) => [xOffset + (lon - b.min_lon) * scale, MAP_HEIGHT - yOffset - (lat - b.min_lat) * scale];
  }, [city]);

  const line = useMemo(() => d3.line().x((d) => projection(d)[0]).y((d) => projection(d)[1]), [projection]);
  const vehicles = useMemo(() => city.trips.map((trip) => {
    const xy = interpolateTrip(trip, seconds);
    return xy ? { id: `${trip.agencyId}-${trip.id}`, xy: projection(xy), agencyId: trip.agencyId } : null;
  }).filter(Boolean), [city, seconds, projection]);

  return <article className="panel city-map">
    <header>
      <div>
        <h2>{city.city}</h2>
        <p>{city.agencies.map((agency) => agency.name).join(' + ')}</p>
      </div>
      <time>{formatTime(seconds)}</time>
    </header>
    <svg viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} role="img" aria-label={`Combined scheduled transit service for ${city.city}`}>
      <g className="routes">
        {city.shapes.slice(0, 1800).map((shape) => <path key={`${shape.agencyId}-${shape.id}`} d={line(shape.points)} />)}
      </g>
      <g className="vehicles">
        {vehicles.map((v) => <circle key={v.id} cx={v.xy[0]} cy={v.xy[1]} r="2.2" />)}
      </g>
    </svg>
    <footer>
      {vehicles.length.toLocaleString()} active scheduled trips · {city.trips.length.toLocaleString()} sampled trips · {city.agencies.length} GTFS feed{city.agencies.length === 1 ? '' : 's'} · {city.serviceDates.join(', ')}
    </footer>
  </article>;
}

function App() {
  const [agencies, setAgencies] = useState([]);
  const [error, setError] = useState(null);
  const seconds = useSimulationClock();
  const cities = useMemo(() => groupAgenciesByCity(agencies), [agencies]);

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
      <h1>One combined map per city</h1>
      <p>Each city rolls every processed GTFS feed into a single no-basemap view, so bus and rail agencies appear together instead of as separate small multiples.</p>
    </section>
    {error && <p className="error">Could not load processed data: {error}</p>}
    {!error && agencies.length === 0 && <p className="loading">Loading processed GTFS datasets…</p>}
    <section className="grid">
      {cities.map((city) => <CityMap key={city.id} city={city} seconds={seconds} />)}
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
