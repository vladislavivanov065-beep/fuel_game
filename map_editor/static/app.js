'use strict';

// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------

const MARI_EL_CENTER = [56.6389, 47.8845]; // same default view fuel_game's own frontend uses
const MARI_EL_ZOOM = 8;
const SNAP_PX = 12; // on-screen pixel radius for vertex snapping while drawing

let project = { roads: [], stations: [], refinery: null, traffic_lights: [] };
let mode = 'select';
let idSeq = 1;
let currentRoadPoints = []; // array of [lon, lat]
let selected = null; // { type: 'road'|'station'|'refinery'|'light', id }
let lastValidation = {}; // light id -> {ok, degree, message}

function newId(prefix) {
  return `${prefix}-${idSeq++}-${Date.now().toString(36)}`;
}

function currentProjectName() {
  return document.getElementById('project-name').value.trim() || 'default';
}

function setStatus(text) {
  document.getElementById('status-line').textContent = text;
}

// ---------------------------------------------------------------------
// Map + layers
// ---------------------------------------------------------------------

const map = L.map('map').setView(MARI_EL_CENTER, MARI_EL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 19,
}).addTo(map);

const roadsLayer = L.layerGroup().addTo(map);
const stationsLayer = L.layerGroup().addTo(map);
const refineryLayer = L.layerGroup().addTo(map);
const lightsLayer = L.layerGroup().addTo(map);
const verticesLayer = L.layerGroup().addTo(map);
const draftLayer = L.layerGroup().addTo(map);

const ROAD_COLORS = { local: '#2563eb', trunk: '#dc2626', primary: '#ea580c' };

// ---------------------------------------------------------------------
// Snapping helpers
// ---------------------------------------------------------------------

function allRoadVertices() {
  const pts = [];
  for (const road of project.roads) {
    for (const c of road.coordinates) pts.push(c);
  }
  for (const p of currentRoadPoints) pts.push(p);
  return pts;
}

function snapToNearestVertex(latlng, candidates, pxRadius) {
  const clickPt = map.latLngToContainerPoint(latlng);
  let best = null;
  let bestDist = Infinity;
  for (const [lon, lat] of candidates) {
    const pt = map.latLngToContainerPoint(L.latLng(lat, lon));
    const dist = clickPt.distanceTo(pt);
    if (dist < bestDist) {
      bestDist = dist;
      best = [lon, lat];
    }
  }
  if (best && bestDist <= pxRadius) return best;
  return [latlng.lng, latlng.lat];
}

// ---------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------

function render() {
  roadsLayer.clearLayers();
  stationsLayer.clearLayers();
  refineryLayer.clearLayers();
  lightsLayer.clearLayers();
  verticesLayer.clearLayers();

  for (const road of project.roads) {
    const latlngs = road.coordinates.map(([lon, lat]) => [lat, lon]);
    const isSel = selected && selected.type === 'road' && selected.id === road.id;
    const line = L.polyline(latlngs, {
      color: ROAD_COLORS[road.road_type] || '#555',
      weight: isSel ? 7 : 4,
      opacity: isSel ? 1 : 0.8,
      dashArray: road.oneway ? '8 6' : null,
    });
    line.on('click', featureClickHandler('road', road.id));
    line.addTo(roadsLayer);
  }

  for (const station of project.stations) {
    const isSel = selected && selected.type === 'station' && selected.id === station.id;
    const marker = L.circleMarker([station.lat, station.lon], {
      radius: isSel ? 9 : 6,
      color: '#0f766e',
      fillColor: '#14b8a6',
      fillOpacity: 0.9,
      weight: 2,
    });
    marker.bindTooltip(station.name);
    marker.on('click', featureClickHandler('station', station.id));
    marker.addTo(stationsLayer);
  }

  if (project.refinery) {
    const r = project.refinery;
    const isSel = selected && selected.type === 'refinery';
    const marker = L.circleMarker([r.lat, r.lon], {
      radius: isSel ? 11 : 8,
      color: '#7c2d12',
      fillColor: '#f97316',
      fillOpacity: 0.95,
      weight: 2,
    });
    marker.bindTooltip(r.name || 'НПЗ');
    marker.on('click', featureClickHandler('refinery', 'refinery'));
    marker.addTo(refineryLayer);
  }

  for (const light of project.traffic_lights) {
    const isSel = selected && selected.type === 'light' && selected.id === light.id;
    const v = lastValidation[light.id];
    let fill = '#9ca3af'; // not yet validated
    if (v) fill = v.ok ? '#16a34a' : '#dc2626';
    const marker = L.circleMarker([light.lat, light.lon], {
      radius: isSel ? 9 : 6,
      color: '#1f2937',
      fillColor: fill,
      fillOpacity: 1,
      weight: 2,
    });
    marker.bindTooltip(v ? v.message : 'Не проверено — нажмите «Проверить светофоры»');
    marker.on('click', featureClickHandler('light', light.id));
    marker.addTo(lightsLayer);
  }

  if (mode === 'road') {
    for (const [lon, lat] of allRoadVertices()) {
      L.circleMarker([lat, lon], {
        radius: 3,
        color: '#94a3b8',
        fillColor: '#cbd5e1',
        fillOpacity: 0.8,
        weight: 1,
      }).addTo(verticesLayer);
    }
  }

  renderFeatureList();
  renderPropsPanel();
}

function renderDraft() {
  draftLayer.clearLayers();
  if (currentRoadPoints.length === 0) return;
  const latlngs = currentRoadPoints.map(([lon, lat]) => [lat, lon]);
  L.polyline(latlngs, { color: '#16a34a', weight: 3, dashArray: '4 4' }).addTo(draftLayer);
  for (const [lon, lat] of currentRoadPoints) {
    L.circleMarker([lat, lon], { radius: 4, color: '#16a34a', fillOpacity: 1 }).addTo(draftLayer);
  }
}

function renderFeatureList() {
  const ul = document.getElementById('feature-list');
  ul.innerHTML = '';
  const addItem = (label, type, id) => {
    const li = document.createElement('li');
    const span = document.createElement('span');
    span.textContent = label;
    span.addEventListener('click', () => selectFeature(type, id));
    const del = document.createElement('span');
    del.textContent = '✕';
    del.className = 'del';
    del.title = 'Удалить';
    del.addEventListener('click', (ev) => {
      ev.stopPropagation();
      deleteFeature(type, id);
    });
    li.appendChild(span);
    li.appendChild(del);
    ul.appendChild(li);
  };
  for (const road of project.roads) {
    addItem(`Дорога [${road.road_type}] ${road.coordinates.length} т.`, 'road', road.id);
  }
  for (const s of project.stations) {
    addItem(`АЗС: ${s.name}`, 'station', s.id);
  }
  if (project.refinery) {
    addItem(`НПЗ: ${project.refinery.name}`, 'refinery', 'refinery');
  }
  for (const l of project.traffic_lights) {
    addItem(`Светофор ${l.id}`, 'light', l.id);
  }
}

// ---------------------------------------------------------------------
// Selection + properties panel
// ---------------------------------------------------------------------

function selectFeature(type, id) {
  if (mode !== 'select') setMode('select');
  selected = { type, id };
  render();
}

function findRoad(id) { return project.roads.find((r) => r.id === id); }
function findStation(id) { return project.stations.find((s) => s.id === id); }
function findLight(id) { return project.traffic_lights.find((l) => l.id === id); }

function deleteFeature(type, id) {
  if (type === 'road') project.roads = project.roads.filter((r) => r.id !== id);
  if (type === 'station') project.stations = project.stations.filter((s) => s.id !== id);
  if (type === 'refinery') project.refinery = null;
  if (type === 'light') project.traffic_lights = project.traffic_lights.filter((l) => l.id !== id);
  if (selected && selected.type === type && selected.id === id) selected = null;
  render();
}

function renderPropsPanel() {
  const body = document.getElementById('props-body');
  if (!selected) {
    body.innerHTML = '<p class="hint">Выберите объект на карте (режим «Выбрать»), чтобы посмотреть или изменить его свойства.</p>';
    return;
  }

  if (selected.type === 'road') {
    const road = findRoad(selected.id);
    if (!road) { selected = null; return renderPropsPanel(); }
    body.innerHTML = `
      <label>Тип дороги
        <select id="p-road-type">
          <option value="local">local</option>
          <option value="trunk">trunk</option>
          <option value="primary">primary</option>
        </select>
      </label>
      <label>Макс. скорость, км/ч<input id="p-road-speed" type="number" min="1" /></label>
      <label class="row"><input id="p-road-oneway" type="checkbox" /> Одностороннее движение</label>
      <button id="p-save">Сохранить</button>
      <button id="p-delete">Удалить</button>
    `;
    document.getElementById('p-road-type').value = road.road_type;
    document.getElementById('p-road-speed').value = road.max_speed_kmh;
    document.getElementById('p-road-oneway').checked = road.oneway;
    document.getElementById('p-save').onclick = () => {
      road.road_type = document.getElementById('p-road-type').value;
      road.max_speed_kmh = parseFloat(document.getElementById('p-road-speed').value) || 50;
      road.oneway = document.getElementById('p-road-oneway').checked;
      render();
    };
    document.getElementById('p-delete').onclick = () => deleteFeature('road', road.id);
  }

  if (selected.type === 'station') {
    const station = findStation(selected.id);
    if (!station) { selected = null; return renderPropsPanel(); }
    body.innerHTML = `
      <label>osm_id (уникальный)<input id="p-st-osm" /></label>
      <label>Название<input id="p-st-name" /></label>
      <label>Базовая цена, ₽<input id="p-st-price" type="number" min="0" step="1" /></label>
      <label>Населённый пункт<input id="p-st-settlement" /></label>
      <button id="p-save">Сохранить</button>
      <button id="p-delete">Удалить</button>
    `;
    document.getElementById('p-st-osm').value = station.osm_id;
    document.getElementById('p-st-name').value = station.name;
    document.getElementById('p-st-price').value = station.base_price_rub;
    document.getElementById('p-st-settlement').value = station.settlement;
    document.getElementById('p-save').onclick = () => {
      station.osm_id = document.getElementById('p-st-osm').value.trim() || station.osm_id;
      station.name = document.getElementById('p-st-name').value.trim() || station.name;
      station.base_price_rub = parseFloat(document.getElementById('p-st-price').value) || 0;
      station.settlement = document.getElementById('p-st-settlement').value.trim();
      render();
    };
    document.getElementById('p-delete').onclick = () => deleteFeature('station', station.id);
  }

  if (selected.type === 'refinery') {
    const r = project.refinery;
    if (!r) { selected = null; return renderPropsPanel(); }
    body.innerHTML = `
      <label>Название<input id="p-rf-name" /></label>
      <button id="p-save">Сохранить</button>
      <button id="p-delete">Удалить</button>
    `;
    document.getElementById('p-rf-name').value = r.name;
    document.getElementById('p-save').onclick = () => {
      r.name = document.getElementById('p-rf-name').value.trim() || r.name;
      render();
    };
    document.getElementById('p-delete').onclick = () => deleteFeature('refinery', 'refinery');
  }

  if (selected.type === 'light') {
    const light = findLight(selected.id);
    if (!light) { selected = null; return renderPropsPanel(); }
    const v = lastValidation[light.id];
    body.innerHTML = `
      <p>${v ? v.message : 'Не проверено. Нажмите «Проверить светофоры» в верхней панели.'}</p>
      <button id="p-delete">Удалить</button>
    `;
    document.getElementById('p-delete').onclick = () => deleteFeature('light', light.id);
  }
}

// ---------------------------------------------------------------------
// Modal helper
// ---------------------------------------------------------------------

function openModal(html) {
  document.getElementById('modal-box').innerHTML = html;
  document.getElementById('modal-overlay').classList.remove('hidden');
}
function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
}

// ---------------------------------------------------------------------
// Mode switching
// ---------------------------------------------------------------------

function setMode(newMode) {
  if (mode === 'road' && newMode !== 'road' && currentRoadPoints.length > 0) {
    if (!confirm('Прервать рисование текущей дороги без сохранения?')) return;
  }
  mode = newMode;
  currentRoadPoints = [];
  renderDraft();
  document.querySelectorAll('.mode-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
  document.getElementById('road-controls').classList.toggle('hidden', mode !== 'road');
  render();
}

document.querySelectorAll('.mode-btn').forEach((btn) => {
  btn.addEventListener('click', () => setMode(btn.dataset.mode));
});

// ---------------------------------------------------------------------
// Map click handling per mode
// ---------------------------------------------------------------------

// Shared by the base map's click handler *and* by every rendered feature
// layer: Leaflet stops a vector layer's own click event from bubbling up to
// the map, so without this, clicking exactly on an existing road/marker
// while in a placement mode (most common case for traffic lights, which
// belong right on top of a road intersection) would silently do nothing.
function handleMapClick(latlng) {
  if (mode === 'road') {
    const snapped = snapToNearestVertex(latlng, allRoadVertices(), SNAP_PX);
    currentRoadPoints.push(snapped);
    renderDraft();
    return;
  }

  if (mode === 'station') {
    openStationForm(latlng.lng, latlng.lat);
    return;
  }

  if (mode === 'refinery') {
    if (project.refinery && !confirm('НПЗ уже задан. Заменить его новой точкой?')) return;
    openRefineryForm(latlng.lng, latlng.lat);
    return;
  }

  if (mode === 'light') {
    const snapped = snapToNearestVertex(latlng, allRoadVertices(), SNAP_PX);
    project.traffic_lights.push({ id: newId('light'), lon: snapped[0], lat: snapped[1] });
    lastValidation = {};
    render();
    return;
  }
}

map.on('click', (ev) => handleMapClick(ev.latlng));

function featureClickHandler(type, id) {
  return (ev) => {
    L.DomEvent.stopPropagation(ev); // otherwise the click also reaches map.on('click') below
    if (mode === 'select') {
      selectFeature(type, id);
    } else {
      handleMapClick(ev.latlng);
    }
  };
}

function openStationForm(lon, lat) {
  openModal(`
    <h3>Новая АЗС</h3>
    <label>osm_id (уникальный)<input id="m-st-osm" value="custom-${idSeq}" /></label>
    <label>Название<input id="m-st-name" value="АЗС" /></label>
    <label>Базовая цена, ₽<input id="m-st-price" type="number" min="0" step="1" value="35000" /></label>
    <label>Населённый пункт<input id="m-st-settlement" /></label>
    <div class="actions">
      <button id="m-cancel">Отмена</button>
      <button id="m-ok">Добавить</button>
    </div>
  `);
  document.getElementById('m-cancel').onclick = closeModal;
  document.getElementById('m-ok').onclick = () => {
    project.stations.push({
      id: newId('station'),
      osm_id: document.getElementById('m-st-osm').value.trim() || `custom-${idSeq}`,
      name: document.getElementById('m-st-name').value.trim() || 'АЗС',
      base_price_rub: parseFloat(document.getElementById('m-st-price').value) || 0,
      settlement: document.getElementById('m-st-settlement').value.trim(),
      lon, lat,
    });
    closeModal();
    render();
  };
}

function openRefineryForm(lon, lat) {
  openModal(`
    <h3>НПЗ (нефтебаза)</h3>
    <label>Название<input id="m-rf-name" value="Нефтебаза" /></label>
    <div class="actions">
      <button id="m-cancel">Отмена</button>
      <button id="m-ok">Добавить / заменить</button>
    </div>
  `);
  document.getElementById('m-cancel').onclick = closeModal;
  document.getElementById('m-ok').onclick = () => {
    project.refinery = {
      name: document.getElementById('m-rf-name').value.trim() || 'Нефтебаза',
      lon, lat,
    };
    closeModal();
    render();
  };
}

function openRoadForm() {
  if (currentRoadPoints.length < 2) {
    alert('Нужно минимум 2 точки для дороги.');
    return;
  }
  openModal(`
    <h3>Новая дорога (${currentRoadPoints.length} точек)</h3>
    <label>Тип дороги
      <select id="m-road-type">
        <option value="local">local</option>
        <option value="trunk">trunk</option>
        <option value="primary">primary</option>
      </select>
    </label>
    <label>Макс. скорость, км/ч<input id="m-road-speed" type="number" min="1" value="50" /></label>
    <label class="row"><input id="m-road-oneway" type="checkbox" /> Одностороннее движение</label>
    <div class="actions">
      <button id="m-cancel">Отмена</button>
      <button id="m-ok">Добавить дорогу</button>
    </div>
  `);
  document.getElementById('m-cancel').onclick = closeModal;
  document.getElementById('m-ok').onclick = () => {
    project.roads.push({
      id: newId('road'),
      road_type: document.getElementById('m-road-type').value,
      max_speed_kmh: parseFloat(document.getElementById('m-road-speed').value) || 50,
      oneway: document.getElementById('m-road-oneway').checked,
      coordinates: currentRoadPoints,
    });
    currentRoadPoints = [];
    renderDraft();
    closeModal();
    render();
  };
}

document.getElementById('btn-finish-road').addEventListener('click', openRoadForm);
document.getElementById('btn-cancel-road').addEventListener('click', () => {
  currentRoadPoints = [];
  renderDraft();
});

document.addEventListener('keydown', (ev) => {
  if (mode !== 'road') return;
  if (ev.key === 'Enter') openRoadForm();
  if (ev.key === 'Escape') {
    currentRoadPoints = [];
    renderDraft();
  }
});

// ---------------------------------------------------------------------
// Save / load
// ---------------------------------------------------------------------

async function saveProject() {
  const name = currentProjectName();
  const res = await fetch(`/api/project?name=${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(project),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error || 'Не удалось сохранить проект');
  }
  return res.json();
}

async function loadProject() {
  const name = currentProjectName();
  const res = await fetch(`/api/project?name=${encodeURIComponent(name)}`);
  const data = await res.json();
  project = data;
  selected = null;
  lastValidation = {};
  render();
  const bounds = computeBounds();
  if (bounds) map.fitBounds(bounds, { padding: [30, 30] });
}

function computeBounds() {
  const pts = [];
  for (const r of project.roads) for (const [lon, lat] of r.coordinates) pts.push([lat, lon]);
  for (const s of project.stations) pts.push([s.lat, s.lon]);
  if (project.refinery) pts.push([project.refinery.lat, project.refinery.lon]);
  for (const l of project.traffic_lights) pts.push([l.lat, l.lon]);
  if (pts.length === 0) return null;
  return L.latLngBounds(pts);
}

async function refreshProjectList() {
  const res = await fetch('/api/projects');
  const data = await res.json();
  const select = document.getElementById('project-list');
  select.innerHTML = '<option value="">— сохранённые проекты —</option>';
  for (const name of data.projects) {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  }
}

document.getElementById('btn-save').addEventListener('click', async () => {
  try {
    await saveProject();
    setStatus(`Сохранено: ${currentProjectName()}`);
    refreshProjectList();
  } catch (e) {
    setStatus('Ошибка сохранения: ' + e.message);
  }
});

document.getElementById('btn-load').addEventListener('click', async () => {
  try {
    await loadProject();
    setStatus(`Загружено: ${currentProjectName()}`);
  } catch (e) {
    setStatus('Ошибка загрузки: ' + e.message);
  }
});

document.getElementById('project-list').addEventListener('change', (ev) => {
  if (!ev.target.value) return;
  document.getElementById('project-name').value = ev.target.value;
  document.getElementById('btn-load').click();
});

// ---------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------

function downloadUrl(url) {
  const a = document.createElement('a');
  a.href = url;
  a.click();
}

async function ensureSaved() {
  await saveProject();
}

document.getElementById('btn-export-roads').addEventListener('click', async () => {
  await ensureSaved();
  downloadUrl(`/api/export/roads.geojson?name=${encodeURIComponent(currentProjectName())}`);
});

document.getElementById('btn-export-stations').addEventListener('click', async () => {
  await ensureSaved();
  downloadUrl(`/api/export/stations.geojson?name=${encodeURIComponent(currentProjectName())}`);
});

document.getElementById('btn-export-refinery').addEventListener('click', async () => {
  await ensureSaved();
  if (!project.refinery) {
    alert('Сначала поставьте точку НПЗ.');
    return;
  }
  downloadUrl(`/api/export/refinery?name=${encodeURIComponent(currentProjectName())}`);
});

document.getElementById('btn-write-output').addEventListener('click', async () => {
  try {
    await ensureSaved();
    const res = await fetch(`/api/export/write?name=${encodeURIComponent(currentProjectName())}`, {
      method: 'POST',
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Ошибка экспорта');
    let msg = `Записано:\n${data.written.join('\n')}`;
    if (data.traffic_light_warnings.length) {
      msg += `\n\nПредупреждения по светофорам:\n` +
        data.traffic_light_warnings.map((w) => `- ${w.message}`).join('\n');
    }
    alert(msg);
    setStatus('Экспорт записан в map_editor/output/');
  } catch (e) {
    setStatus('Ошибка экспорта: ' + e.message);
  }
});

document.getElementById('btn-validate').addEventListener('click', async () => {
  try {
    await ensureSaved();
    const res = await fetch(`/api/validate?name=${encodeURIComponent(currentProjectName())}`);
    const data = await res.json();
    lastValidation = {};
    for (const c of data.traffic_lights) lastValidation[c.id] = c;
    render();

    const rows = data.traffic_lights
      .map((c) => `<div class="validate-row ${c.ok ? 'ok' : 'warn'}">${c.id}: ${c.message}</div>`)
      .join('') || '<p>Светофоров пока нет на карте.</p>';
    openModal(`
      <h3>Проверка светофоров</h3>
      ${rows}
      <div class="actions"><button id="m-cancel">Закрыть</button></div>
    `);
    document.getElementById('m-cancel').onclick = closeModal;
  } catch (e) {
    setStatus('Ошибка проверки: ' + e.message);
  }
});

// ---------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------

(async function init() {
  await refreshProjectList();
  await loadProject();
  setMode('select');
  setStatus('Готово');
})();
