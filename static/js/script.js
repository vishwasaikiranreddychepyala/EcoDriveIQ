// static/js/script.js — EcoDriveIQ v2.0
// CHANGED: What-If, Fleet, Trend Chart, EV Break-Even, Comparison Table,
//          Fatigue bar, Health bar, Grade color, Anomaly alert, Trees

let trendChartInstance = null;

window.addEventListener('DOMContentLoaded', loadStats);

// ── Load Stats ────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const d = await (await fetch('/stats')).json();
    document.getElementById('sTotalTrips').textContent  = d.total_trips   || 0;
    document.getElementById('sAvgEco').textContent      = d.avg_eco_score || '—';
    document.getElementById('sTotalCost').textContent   = d.total_cost_inr
      ? '₹' + Number(d.total_cost_inr).toLocaleString('en-IN') : '—';
    document.getElementById('sTotalCarbon').textContent = d.total_carbon_kg || '—';
    document.getElementById('sAnomalies').textContent   = d.total_anomalies ?? '—';
    document.getElementById('sEvSavings').textContent   = d.total_ev_savings
      ? '₹' + Number(d.total_ev_savings).toLocaleString('en-IN') : '—';
  } catch (e) { console.warn('Stats:', e.message); }
}

// ── Predict ───────────────────────────────────────────────────────────────────
async function predict() {
  const btn = document.querySelector('.btn-predict');
  const payload = getPayload();
  if (!payload.distance_km || payload.distance_km <= 0) {
    return alert('Please enter a valid distance!');
  }

  btn.innerHTML = '<span class="spinner"></span> Analyzing...';
  btn.disabled  = true;

  try {
    const res  = await fetch('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!data.success) { alert('Error: ' + data.error); return; }

    renderResults(data);
    document.getElementById('resultsPanel').style.display = 'block';
    document.getElementById('resultsPanel').scrollIntoView({ behavior: 'smooth' });
    loadStats();
  } catch(e) {
    alert('Server connection error. Is Flask running?');
  } finally {
    btn.innerHTML = '⚡ Analyze Trip Intelligence';
    btn.disabled  = false;
  }
}

function renderResults(d) {
  // Core predictions
  document.getElementById('rFuel').textContent   = d.fuel_consumed_litres + ' L';
  document.getElementById('rCost').textContent   = '₹' + d.trip_cost_inr;
  document.getElementById('rCarbon').textContent = d.carbon_emission_kg + ' kg';
  document.getElementById('rTrees').textContent  = d.trees_equivalent;
  document.getElementById('rOffset').textContent = '₹' + d.carbon_offset_inr;

  // Eco Score ring
  animateEcoRing(d.eco_score);

  // Trip Grade
  const gradeColors = { A: '#2ed573', B: '#00f5d4', C: '#f7b731', D: '#ffa502', F: '#ff4757' };
  const gv = document.getElementById('gradeVal');
  const gl = document.getElementById('gradeLabel');
  const gb = document.getElementById('gradeBox');
  gv.textContent = d.trip_grade;
  gl.textContent = d.trip_grade_label;
  gv.style.color = gradeColors[d.trip_grade] || '#fff';
  gb.style.borderColor = gradeColors[d.trip_grade] || 'transparent';

  // Fatigue bar
  const fb = document.getElementById('fatigueBar');
  fb.style.width = d.fatigue_risk + '%';
  fb.style.background = d.fatigue_risk > 70 ? '#ff4757' : d.fatigue_risk > 45 ? '#ffa502' : '#2ed573';
  document.getElementById('fatigueVal').textContent = d.fatigue_risk;

  // Health/Maintenance bar
  const mb = document.getElementById('maintBar');
  mb.style.width = d.maintenance_score + '%';
  mb.style.background = d.maintenance_score < 40 ? '#ff4757' : d.maintenance_score < 65 ? '#ffa502' : '#2ed573';
  document.getElementById('maintVal').textContent = d.maintenance_score;

  // Alerts
  document.getElementById('anomalyAlert').style.display  = d.is_anomaly   ? 'block' : 'none';
  document.getElementById('fatigueAlert').style.display  = d.fatigue_risk > 70 ? 'block' : 'none';

  // Comparison table
  document.getElementById('cPetrolTrip').textContent   = '₹' + d.trip_cost_inr;
  document.getElementById('cPetrolMonth').textContent  = '₹' + d.monthly_petrol.toLocaleString('en-IN');
  document.getElementById('cPetrolYear').textContent   = '₹' + d.annual_petrol.toLocaleString('en-IN');
  document.getElementById('cCngTrip').textContent      = '₹' + d.cng_cost_per_trip;
  document.getElementById('cCngMonth').textContent     = '₹' + d.monthly_cng.toLocaleString('en-IN');
  document.getElementById('cCngYear').textContent      = '₹' + d.annual_cng.toLocaleString('en-IN');
  document.getElementById('cCngSave').textContent      = '↓ ₹' + d.annual_savings_cng.toLocaleString('en-IN') + '/yr';
  document.getElementById('cEvTrip').textContent       = '₹' + d.ev_cost_per_trip;
  document.getElementById('cEvMonth').textContent      = '₹' + d.monthly_ev.toLocaleString('en-IN');
  document.getElementById('cEvYear').textContent       = '₹' + d.annual_ev.toLocaleString('en-IN');
  document.getElementById('cEvSave').textContent       = '↓ ₹' + d.annual_savings_ev.toLocaleString('en-IN') + '/yr';

  // EV break-even
  const evt = document.getElementById('evBreakEvenText');
  if (d.ev_breakeven_months) {
    evt.innerHTML = `
      Switching to EV saves you <strong style="color:var(--success)">₹${d.annual_savings_ev.toLocaleString('en-IN')}/year</strong>.
      At an EV premium of ₹3,00,000 over an equivalent ICE vehicle, you break even in
      <strong style="color:var(--accent3)">${d.ev_breakeven_months} months (${d.ev_breakeven_years} years)</strong>.
      After that, you pocket ₹${d.annual_savings_ev.toLocaleString('en-IN')} every year in pure savings.
    `;
  } else {
    evt.textContent = 'EV is not cheaper for this trip profile. Consider CNG as a stepping stone.';
  }

  // Fuel price impact
  document.getElementById('rAt110').textContent = '₹' + d.cost_at_110;
  document.getElementById('rAt120').textContent = '₹' + d.cost_at_120;
  document.getElementById('rAt130').textContent = '₹' + d.cost_at_130;

  // Recommendations
  const html = d.recommendations.map(r => `<p>→ ${r}</p>`).join('');
  document.getElementById('recText').innerHTML = html;
}

// ── Eco Score Ring Animation ──────────────────────────────────────────────────
function animateEcoRing(score) {
  const circle = document.getElementById('ecoCircle');
  const offset = 314 - (score / 100) * 314;
  circle.style.transition = 'none';
  circle.style.strokeDashoffset = 314;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    circle.style.transition = 'stroke-dashoffset 1.3s cubic-bezier(.4,0,.2,1)';
    circle.style.strokeDashoffset = offset;
    const color = score >= 70 ? '#00f5d4' : score >= 45 ? '#f7b731' : '#ff4757';
    circle.style.stroke = color;
    document.getElementById('ecoScoreVal').textContent = score;
    document.getElementById('ecoScoreVal').style.color = color;
  }));
}

// ── What-If Optimizer ─────────────────────────────────────────────────────────
async function runWhatIf() {
  const payload = getPayload();
  if (!payload.distance_km) return alert('Enter trip details first!');

  try {
    const res  = await fetch('/whatsif', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const d = await res.json();
    if (!d.success) { alert(d.error); return; }

    const sec = document.getElementById('whatIfSection');
    document.getElementById('whatIfGrid').innerHTML = `
      <div class="wi-box">
        <h4>📊 Base vs Optimized Comparison</h4>
        <div class="wi-row"><span class="wi-label">Fuel Used</span>
          <span><span class="wi-val-base">${d.base_fuel} L</span> → <span class="wi-val-opt">${d.opt_fuel} L</span></span></div>
        <div class="wi-row"><span class="wi-label">Trip Cost</span>
          <span><span class="wi-val-base">₹${d.base_cost}</span> → <span class="wi-val-opt">₹${d.opt_cost}</span></span></div>
        <div class="wi-row"><span class="wi-label">Eco Score</span>
          <span><span class="wi-val-base">${d.base_eco}</span> → <span class="wi-val-opt">${d.opt_eco}</span></span></div>
        <div class="wi-save">💰 Monthly Savings: ₹${d.monthly_savings.toLocaleString('en-IN')}</div>
      </div>
      <div class="wi-box">
        <h4>🛠 Optimizations Applied</h4>
        <div class="wi-row"><span class="wi-label">AC</span><span class="wi-val-opt">Turned Off</span></div>
        <div class="wi-row"><span class="wi-label">Tyre Pressure</span><span class="wi-val-opt">Corrected</span></div>
        <div class="wi-row"><span class="wi-label">Speed</span><span class="wi-val-opt">Capped at 65 km/h</span></div>
        <div class="wi-row"><span class="wi-label">Harsh Braking</span><span class="wi-val-opt">Eliminated</span></div>
        <div class="wi-row"><span class="wi-label">Idle Time</span><span class="wi-val-opt">Reduced to 2 min</span></div>
        <div class="wi-save">📅 Annual Savings: ₹${d.annual_savings.toLocaleString('en-IN')}</div>
      </div>
    `;
    sec.style.display = 'block';
    sec.scrollIntoView({ behavior: 'smooth' });
  } catch(e) { alert('What-If error: ' + e.message); }
}

// ── Trip History ──────────────────────────────────────────────────────────────
async function loadHistory() {
  const res  = await fetch('/history');
  const data = await res.json();
  const gc   = { A:'#2ed573', B:'#00f5d4', C:'#f7b731', D:'#ffa502', F:'#ff4757' };
  const body = document.getElementById('historyBody');
  body.innerHTML = '';
  data.trips.forEach((t, i) => {
    const eco_color = t.predicted_eco_score >= 70 ? '#00f5d4' : t.predicted_eco_score >= 45 ? '#f7b731' : '#ff4757';
    body.innerHTML += `
      <tr>
        <td>${data.trips.length - i}</td>
        <td>${(t.timestamp || '').slice(0, 16)}</td>
        <td>${t.vehicle_type}</td>
        <td>${t.distance_km} km</td>
        <td>${t.predicted_fuel} L</td>
        <td>₹${t.predicted_cost}</td>
        <td>${t.predicted_carbon} kg</td>
        <td style="color:${eco_color};font-weight:700">${t.predicted_eco_score}</td>
        <td style="color:${gc[t.trip_grade]||'#fff'};font-weight:800">${t.trip_grade || '—'}</td>
        <td style="color:${t.is_anomaly ? '#ff4757' : '#2ed573'}">${t.is_anomaly ? '⚠ YES' : '✓ No'}</td>
      </tr>`;
  });
  const sec = document.getElementById('historySection');
  sec.style.display = 'block';
  sec.scrollIntoView({ behavior: 'smooth' });
}

// ── Fleet Analytics ───────────────────────────────────────────────────────────
async function loadFleet() {
  const res  = await fetch('/fleet');
  const data = await res.json();
  const body = document.getElementById('fleetBody');
  body.innerHTML = '';
  data.fleet.forEach(f => {
    const eco_color = f.avg_eco >= 70 ? '#00f5d4' : f.avg_eco >= 45 ? '#f7b731' : '#ff4757';
    body.innerHTML += `
      <tr>
        <td><strong>${f.vehicle}</strong></td>
        <td>${f.trips}</td>
        <td style="color:${eco_color};font-weight:700">${f.avg_eco}</td>
        <td>${f.avg_fuel} L</td>
        <td>₹${Number(f.total_cost).toLocaleString('en-IN')}</td>
        <td>${f.avg_maint}</td>
        <td style="color:${f.anomalies > 0 ? '#ff4757' : '#2ed573'}">${f.anomalies}</td>
      </tr>`;
  });
  const sec = document.getElementById('fleetSection');
  sec.style.display = 'block';
  sec.scrollIntoView({ behavior: 'smooth' });
}

// ── 7-Day Trend Chart ─────────────────────────────────────────────────────────
async function loadTrend() {
  const res  = await fetch('/trend');
  const data = await res.json();

  const labels = data.trend.map(t => t.day);
  const ecos   = data.trend.map(t => t.avg_eco);
  const costs  = data.trend.map(t => t.total_cost);

  if (trendChartInstance) trendChartInstance.destroy();

  const ctx = document.getElementById('trendChart').getContext('2d');
  trendChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Avg Eco Score',
          data: ecos,
          borderColor: '#00f5d4',
          backgroundColor: 'rgba(0,245,212,0.1)',
          tension: 0.4, fill: true, yAxisID: 'y'
        },
        {
          label: 'Total Cost (₹)',
          data: costs,
          borderColor: '#f7b731',
          backgroundColor: 'rgba(247,183,49,0.1)',
          tension: 0.4, fill: false, yAxisID: 'y1'
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#8892b0' } } },
      scales: {
        x:  { ticks: { color: '#8892b0' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y:  { ticks: { color: '#00f5d4' }, grid: { color: 'rgba(255,255,255,0.05)' },
              title: { display: true, text: 'Eco Score', color: '#00f5d4' } },
        y1: { position: 'right', ticks: { color: '#f7b731' },
              grid: { drawOnChartArea: false },
              title: { display: true, text: 'Cost (₹)', color: '#f7b731' } }
      }
    }
  });

  const sec = document.getElementById('trendSection');
  sec.style.display = 'block';
  sec.scrollIntoView({ behavior: 'smooth' });
}

// ── Payload Builder ───────────────────────────────────────────────────────────
function getPayload() {
  return {
    vehicle_type:         document.getElementById('vehicle_type').value,
    fuel_type:            document.getElementById('fuel_type').value,
    road_type:            document.getElementById('road_type').value,
    time_of_day:          document.getElementById('time_of_day').value,
    weather:              document.getElementById('weather').value,
    distance_km:          parseFloat(document.getElementById('distance_km').value)      || 10,
    avg_speed_kmph:       parseFloat(document.getElementById('avg_speed_kmph').value)   || 35,
    traffic_level:        parseInt(document.getElementById('traffic_level').value)       || 3,
    ac_used:              parseInt(document.getElementById('ac_used').value),
    load_kg:              parseFloat(document.getElementById('load_kg').value)           || 80,
    engine_cc:            parseInt(document.getElementById('engine_cc').value)           || 1200,
    tyre_pressure_ok:     parseInt(document.getElementById('tyre_pressure_ok').value),
    last_service_days:    parseInt(document.getElementById('last_service_days').value)   || 30,
    fuel_price_per_litre: parseFloat(document.getElementById('fuel_price_per_litre').value) || 105,
    driver_hours_today:   parseFloat(document.getElementById('driver_hours_today').value) || 4,
    idle_time_minutes:    parseFloat(document.getElementById('idle_time_minutes').value)  || 5,
    harsh_braking_count:  parseInt(document.getElementById('harsh_braking_count').value)  || 2,
    rpm_avg:              parseInt(document.getElementById('rpm_avg').value)              || 1800,
    trips_per_month:      parseInt(document.getElementById('trips_per_month').value)      || 60
  };
}