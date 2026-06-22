# app.py
# EcoDriveIQ v2.0 - Advanced Flask Backend
# CHANGED: Added /trend, /whatsif, /fleet endpoints
#          Added anomaly detection, EV break-even, fatigue risk,
#          carbon offset cost, trip grade, maintenance scoring,
#          savings comparison (Petrol vs CNG vs EV)

from flask import Flask, request, jsonify, render_template
import joblib
import numpy as np
import sqlite3
import os
import csv
from datetime import datetime, timedelta
import math

app = Flask(__name__)

# ─── Load All Models ──────────────────────────────────────────────────────────
print("🔄 Loading AI models...")
fuel_model     = joblib.load('models/fuel_model.pkl')
cost_model     = joblib.load('models/cost_model.pkl')
carbon_model   = joblib.load('models/carbon_model.pkl')
eco_model      = joblib.load('models/eco_model.pkl')
fatigue_model  = joblib.load('models/fatigue_model.pkl')
anomaly_model  = joblib.load('models/anomaly_model.pkl')

le_vehicle   = joblib.load('models/le_vehicle.pkl')
le_fuel      = joblib.load('models/le_fuel.pkl')
le_road      = joblib.load('models/le_road.pkl')
le_time      = joblib.load('models/le_time_of_day.pkl')
le_weather   = joblib.load('models/le_weather.pkl')
FEATURES     = joblib.load('models/features.pkl')
ANOMALY_FEAT = joblib.load('models/anomaly_features.pkl')
print("✅ All models loaded!")

# ─── Database ─────────────────────────────────────────────────────────────────
DB_PATH = 'database/trips.db'
os.makedirs('database', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp             TEXT,
            vehicle_type          TEXT,
            fuel_type             TEXT,
            road_type             TEXT,
            time_of_day           TEXT,
            weather               TEXT,
            distance_km           REAL,
            avg_speed_kmph        REAL,
            traffic_level         INTEGER,
            ac_used               INTEGER,
            load_kg               REAL,
            engine_cc             INTEGER,
            tyre_pressure_ok      INTEGER,
            last_service_days     INTEGER,
            fuel_price_per_litre  REAL,
            driver_hours_today    REAL,
            idle_time_minutes     REAL,
            harsh_braking_count   INTEGER,
            rpm_avg               INTEGER,
            predicted_fuel        REAL,
            predicted_cost        REAL,
            predicted_carbon      REAL,
            predicted_eco_score   REAL,
            predicted_fatigue     REAL,
            trip_grade            TEXT,
            is_anomaly            INTEGER,
            carbon_offset_inr     REAL,
            ev_cost_per_trip      REAL,
            ev_savings_per_trip   REAL,
            maintenance_score     REAL,
            monthly_forecast_inr  REAL,
            annual_forecast_inr   REAL,
            recommendation        TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ─── Helpers ──────────────────────────────────────────────────────────────────
def safe_encode(encoder, value, default=0):
    try:
        return int(encoder.transform([value])[0])
    except:
        return default

def encode_input(d):
    return [
        safe_encode(le_vehicle, d['vehicle_type']),
        safe_encode(le_fuel,    d['fuel_type']),
        safe_encode(le_road,    d['road_type']),
        safe_encode(le_time,    d.get('time_of_day', 'Morning')),
        safe_encode(le_weather, d.get('weather', 'Clear')),
        float(d['distance_km']),
        float(d['avg_speed_kmph']),
        int(d['traffic_level']),
        int(d['ac_used']),
        float(d['load_kg']),
        int(d['engine_cc']),
        int(d['tyre_pressure_ok']),
        int(d['last_service_days']),
        float(d['fuel_price_per_litre']),
        float(d.get('driver_hours_today', 4)),
        float(d.get('idle_time_minutes', 5)),
        int(d.get('harsh_braking_count', 2)),
        int(d.get('rpm_avg', 1800))
    ]

def get_trip_grade(eco):
    if eco >= 85: return 'A'
    elif eco >= 70: return 'B'
    elif eco >= 55: return 'C'
    elif eco >= 40: return 'D'
    else: return 'F'

def get_grade_label(g):
    return {'A':'Excellent','B':'Good','C':'Average','D':'Poor','F':'Critical'}.get(g,'—')

def carbon_offset_cost(carbon_kg):
    # India voluntary carbon market: ~₹800 per tonne CO₂ = ₹0.80 per kg
    return round(carbon_kg * 0.80, 2)

def ev_breakeven(monthly_petrol_cost, monthly_ev_cost):
    savings_per_month = monthly_petrol_cost - monthly_ev_cost
    if savings_per_month <= 0:
        return None, None
    # Avg EV premium in India: ₹3,00,000 over equivalent ICE
    ev_premium = 300000
    months = math.ceil(ev_premium / savings_per_month)
    years  = round(months / 12, 1)
    return months, years

def maintenance_score(last_service_days, tyre_ok, rpm_avg, harsh_braking):
    score = 100
    score -= min(last_service_days / 4, 40)   # service overdue penalty
    score -= (0 if tyre_ok else 15)            # bad tyres
    score -= min((rpm_avg - 1500) / 100, 20)  # high RPM stress
    score -= harsh_braking * 1.5              # harsh braking wear
    return round(max(0, min(100, score)), 1)

def generate_recommendations(d, eco, fuel, fatigue, maint_score, is_anomaly):
    tips = []
    if int(d['ac_used']) == 1:
        tips.append("💨 Turn off AC when possible — saves ₹400–600/month at current prices.")
    if int(d['traffic_level']) >= 4:
        tips.append("🚦 Reschedule trips by 45 min — avoiding peak traffic saves 18–25% fuel.")
    if int(d['last_service_days']) > 90:
        tips.append("🔧 Your vehicle is overdue for service — every 30 days delay costs ~2% efficiency.")
    if int(d['tyre_pressure_ok']) == 0:
        tips.append("🛞 Inflate tyres to recommended PSI — saves 3–5% fuel per trip.")
    if float(d['avg_speed_kmph']) > 72:
        tips.append("⚡ Reduce speed to 60–70 kmph — aerodynamic drag above 70 kills mileage fast.")
    if float(d.get('idle_time_minutes', 0)) > 10:
        tips.append("🅿️ Excessive idle time detected — turn engine off when stopped >1 min.")
    if int(d.get('harsh_braking_count', 0)) > 5:
        tips.append("🛑 Reduce harsh braking — anticipate stops 50m ahead, save fuel & brake pads.")
    if fatigue > 70:
        tips.append("😴 HIGH FATIGUE RISK — consider a break. Fatigue increases accidents 3× and fuel waste 12%.")
    if maint_score < 50:
        tips.append("⚠️ Vehicle health is degrading — schedule a full inspection immediately.")
    if is_anomaly:
        tips.append("🔍 ANOMALY DETECTED — your fuel consumption is statistically abnormal. Check for fuel leaks or engine issues.")
    if eco < 50:
        tips.append("🌿 Eco Score critical — switching to CNG could cut your fuel cost by 40–50%.")
    if not tips:
        tips.append("✅ Outstanding driving behavior! You are in the top 15% of eco-drivers.")
    return tips

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/predict', methods=['POST'])
def predict():
    try:
        d = request.get_json()
        features  = encode_input(d)
        X         = np.array(features).reshape(1, -1)

        # ── Core Predictions ────────────────────────────────────────────────
        fuel    = round(float(fuel_model.predict(X)[0]),    3)
        cost    = round(float(cost_model.predict(X)[0]),    2)
        carbon  = round(float(carbon_model.predict(X)[0]),  3)
        eco     = round(float(eco_model.predict(X)[0]),     1)
        fatigue = round(float(fatigue_model.predict(X)[0]), 1)
        eco     = max(0, min(100, eco))
        fatigue = max(0, min(100, fatigue))

        # ── Anomaly Detection ───────────────────────────────────────────────
        X_anomaly = np.array([
            float(d['distance_km']), fuel, float(d['avg_speed_kmph']),
            int(d['traffic_level']), float(d.get('idle_time_minutes', 5)),
            int(d.get('harsh_braking_count', 2))
        ]).reshape(1, -1)
        anomaly_pred = anomaly_model.predict(X_anomaly)[0]
        is_anomaly   = int(anomaly_pred == -1)

        # ── Trip Grade ──────────────────────────────────────────────────────
        grade       = get_trip_grade(eco)
        grade_label = get_grade_label(grade)

        # ── Carbon Offset Cost ──────────────────────────────────────────────
        carbon_offset = carbon_offset_cost(carbon)

        # ── EV Economics ────────────────────────────────────────────────────
        ev_cost       = round((float(d['distance_km']) / 100) * 15 * 8, 2)
        ev_savings    = round(cost - ev_cost, 2)
        trips_pm      = int(d.get('trips_per_month', 60))
        monthly_cost  = round(cost   * trips_pm, 2)
        monthly_ev    = round(ev_cost * trips_pm, 2)
        ev_months, ev_years = ev_breakeven(monthly_cost, monthly_ev)

        # ── CNG Comparison ──────────────────────────────────────────────────
        cng_cost_per_trip = round(fuel * 75, 2)   # CNG avg ₹75/kg in India
        cng_savings       = round(cost - cng_cost_per_trip, 2)
        monthly_cng       = round(cng_cost_per_trip * trips_pm, 2)

        # ── Forecasts ───────────────────────────────────────────────────────
        annual_cost    = round(monthly_cost * 12, 2)
        annual_ev      = round(monthly_ev   * 12, 2)
        annual_cng     = round(monthly_cng  * 12, 2)
        annual_savings_ev  = round(annual_cost - annual_ev,  2)
        annual_savings_cng = round(annual_cost - annual_cng, 2)

        # ── Future Fuel Price Impact ─────────────────────────────────────────
        cost_at_110 = round(fuel * 110, 2)
        cost_at_120 = round(fuel * 120, 2)
        cost_at_130 = round(fuel * 130, 2)

        # ── Maintenance Score ────────────────────────────────────────────────
        maint = maintenance_score(
            int(d['last_service_days']),
            int(d['tyre_pressure_ok']),
            int(d.get('rpm_avg', 1800)),
            int(d.get('harsh_braking_count', 2))
        )

        # ── CO₂ Trees Equivalent ────────────────────────────────────────────
        # 1 tree absorbs ~21kg CO₂/year = 0.0575 kg/day
        trees_equivalent = round(carbon / 0.0575, 1)

        # ── Recommendations ──────────────────────────────────────────────────
        tips = generate_recommendations(d, eco, fuel, fatigue, maint, is_anomaly)

        # ── Save to DB ───────────────────────────────────────────────────────
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute('''
            INSERT INTO trips (
                timestamp, vehicle_type, fuel_type, road_type,
                time_of_day, weather,
                distance_km, avg_speed_kmph, traffic_level, ac_used,
                load_kg, engine_cc, tyre_pressure_ok, last_service_days,
                fuel_price_per_litre, driver_hours_today, idle_time_minutes,
                harsh_braking_count, rpm_avg,
                predicted_fuel, predicted_cost, predicted_carbon,
                predicted_eco_score, predicted_fatigue,
                trip_grade, is_anomaly, carbon_offset_inr,
                ev_cost_per_trip, ev_savings_per_trip,
                maintenance_score, monthly_forecast_inr,
                annual_forecast_inr, recommendation
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            d['vehicle_type'], d['fuel_type'], d['road_type'],
            d.get('time_of_day','Morning'), d.get('weather','Clear'),
            d['distance_km'], d['avg_speed_kmph'], d['traffic_level'],
            d['ac_used'], d['load_kg'], d['engine_cc'],
            d['tyre_pressure_ok'], d['last_service_days'],
            d['fuel_price_per_litre'],
            d.get('driver_hours_today', 4), d.get('idle_time_minutes', 5),
            d.get('harsh_braking_count', 2), d.get('rpm_avg', 1800),
            fuel, cost, carbon, eco, fatigue,
            grade, is_anomaly, carbon_offset,
            ev_cost, ev_savings, maint,
            monthly_cost, annual_cost, ' | '.join(tips)
        ))
        conn.commit()
        conn.close()

        return jsonify({
            'success':               True,
            # Core
            'fuel_consumed_litres':  fuel,
            'trip_cost_inr':         cost,
            'carbon_emission_kg':    carbon,
            'eco_score':             eco,
            # Advanced
            'fatigue_risk':          fatigue,
            'trip_grade':            grade,
            'trip_grade_label':      grade_label,
            'is_anomaly':            is_anomaly,
            'carbon_offset_inr':     carbon_offset,
            'trees_equivalent':      trees_equivalent,
            'maintenance_score':     maint,
            # EV & CNG
            'ev_cost_per_trip':      ev_cost,
            'ev_savings_per_trip':   ev_savings,
            'cng_cost_per_trip':     cng_cost_per_trip,
            'cng_savings_per_trip':  cng_savings,
            'ev_breakeven_months':   ev_months,
            'ev_breakeven_years':    ev_years,
            # Forecasts
            'monthly_petrol':        monthly_cost,
            'monthly_cng':           monthly_cng,
            'monthly_ev':            monthly_ev,
            'annual_petrol':         annual_cost,
            'annual_cng':            annual_cng,
            'annual_ev':             annual_ev,
            'annual_savings_ev':     annual_savings_ev,
            'annual_savings_cng':    annual_savings_cng,
            # Fuel price simulator
            'cost_at_110':           cost_at_110,
            'cost_at_120':           cost_at_120,
            'cost_at_130':           cost_at_130,
            # Tips
            'recommendations':       tips
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/history', methods=['GET'])
def history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM trips ORDER BY id DESC LIMIT 25')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({'success': True, 'trips': rows})


@app.route('/stats', methods=['GET'])
def stats():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute('''
        SELECT
            COUNT(*)                       AS total_trips,
            ROUND(AVG(predicted_fuel), 3)  AS avg_fuel,
            ROUND(SUM(predicted_cost), 2)  AS total_cost,
            ROUND(AVG(predicted_eco_score),1) AS avg_eco,
            ROUND(SUM(predicted_carbon), 3) AS total_carbon,
            ROUND(AVG(maintenance_score),1) AS avg_maintenance,
            ROUND(AVG(predicted_fatigue),1) AS avg_fatigue,
            SUM(is_anomaly)                AS total_anomalies,
            ROUND(SUM(ev_savings_per_trip),2) AS total_ev_savings
        FROM trips
    ''')
    r = cur.fetchone()
    conn.close()
    return jsonify({
        'total_trips':       r[0] or 0,
        'avg_fuel_litres':   r[1] or 0,
        'total_cost_inr':    r[2] or 0,
        'avg_eco_score':     r[3] or 0,
        'total_carbon_kg':   r[4] or 0,
        'avg_maintenance':   r[5] or 0,
        'avg_fatigue':       r[6] or 0,
        'total_anomalies':   r[7] or 0,
        'total_ev_savings':  r[8] or 0
    })


@app.route('/trend', methods=['GET'])
def trend():
    """Rolling 7-day eco trend for chart"""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute('''
        SELECT
            DATE(timestamp) AS day,
            ROUND(AVG(predicted_eco_score), 1) AS avg_eco,
            ROUND(AVG(predicted_fuel), 3)       AS avg_fuel,
            ROUND(SUM(predicted_cost), 2)        AS total_cost,
            COUNT(*)                             AS trips
        FROM trips
        WHERE timestamp >= DATE('now', '-7 days')
        GROUP BY DATE(timestamp)
        ORDER BY day ASC
    ''')
    rows = [{'day': r[0], 'avg_eco': r[1], 'avg_fuel': r[2],
             'total_cost': r[3], 'trips': r[4]} for r in cur.fetchall()]
    conn.close()
    return jsonify({'success': True, 'trend': rows})


@app.route('/whatsif', methods=['POST'])
def whatsif():
    """What-If Simulator: compare base vs optimized scenario"""
    try:
        d = request.get_json()
        # Base prediction
        features = encode_input(d)
        X        = np.array(features).reshape(1, -1)
        base_fuel = float(fuel_model.predict(X)[0])
        base_cost = float(cost_model.predict(X)[0])
        base_eco  = float(eco_model.predict(X)[0])

        # Optimized scenario: AC off, tyre OK, speed 60, no harsh braking
        d_opt = d.copy()
        d_opt['ac_used']             = 0
        d_opt['tyre_pressure_ok']    = 1
        d_opt['avg_speed_kmph']      = min(65, float(d['avg_speed_kmph']))
        d_opt['harsh_braking_count'] = 0
        d_opt['idle_time_minutes']   = 2
        d_opt['traffic_level']       = max(1, int(d['traffic_level']) - 1)

        features_opt = encode_input(d_opt)
        X_opt        = np.array(features_opt).reshape(1, -1)
        opt_fuel = float(fuel_model.predict(X_opt)[0])
        opt_cost = float(cost_model.predict(X_opt)[0])
        opt_eco  = float(eco_model.predict(X_opt)[0])

        trips_pm = int(d.get('trips_per_month', 60))

        return jsonify({
            'success':          True,
            'base_fuel':        round(base_fuel, 3),
            'base_cost':        round(base_cost, 2),
            'base_eco':         round(base_eco, 1),
            'opt_fuel':         round(opt_fuel, 3),
            'opt_cost':         round(opt_cost, 2),
            'opt_eco':          round(opt_eco, 1),
            'fuel_saved':       round(base_fuel - opt_fuel, 3),
            'cost_saved':       round(base_cost - opt_cost, 2),
            'eco_improved':     round(opt_eco - base_eco, 1),
            'monthly_savings':  round((base_cost - opt_cost) * trips_pm, 2),
            'annual_savings':   round((base_cost - opt_cost) * trips_pm * 12, 2)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/fleet', methods=['GET'])
def fleet():
    """Fleet-level analytics by vehicle type"""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute('''
        SELECT
            vehicle_type,
            COUNT(*)                            AS trips,
            ROUND(AVG(predicted_eco_score), 1)  AS avg_eco,
            ROUND(AVG(predicted_fuel), 3)        AS avg_fuel,
            ROUND(SUM(predicted_cost), 2)         AS total_cost,
            ROUND(AVG(maintenance_score), 1)      AS avg_maint,
            SUM(is_anomaly)                       AS anomalies
        FROM trips
        GROUP BY vehicle_type
        ORDER BY avg_eco DESC
    ''')
    rows = [{'vehicle': r[0], 'trips': r[1], 'avg_eco': r[2],
             'avg_fuel': r[3], 'total_cost': r[4],
             'avg_maint': r[5], 'anomalies': r[6]} for r in cur.fetchall()]
    conn.close()
    return jsonify({'success': True, 'fleet': rows})


@app.route('/export', methods=['GET'])
def export_csv():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute('SELECT * FROM trips')
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    conn.close()
    os.makedirs('data', exist_ok=True)
    with open('data/trips_export.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)
    return jsonify({'success': True, 'message': 'Exported → data/trips_export.csv'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)