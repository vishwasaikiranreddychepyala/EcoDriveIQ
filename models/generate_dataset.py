# models/generate_dataset.py
# EcoDriveIQ v2.0 - Advanced Dataset Generator
# CHANGED: Added fatigue_risk, trip_grade, anomaly_flag, ev_equivalent_cost columns

import pandas as pd
import numpy as np
import os

np.random.seed(42)
N = 8000

vehicle_types  = ['Car', 'Bike', 'Truck', 'Auto', 'SUV']
fuel_types     = ['Petrol', 'Diesel', 'CNG']
road_types     = ['City', 'Highway', 'Mixed']
time_of_days   = ['Morning', 'Afternoon', 'Evening', 'Night']
weather_conds  = ['Clear', 'Rain', 'Fog', 'Hot']

vehicle_type  = np.random.choice(vehicle_types, N, p=[0.40, 0.30, 0.10, 0.10, 0.10])
fuel_type     = np.random.choice(fuel_types,    N, p=[0.55, 0.30, 0.15])
road_type     = np.random.choice(road_types,    N, p=[0.50, 0.25, 0.25])
time_of_day   = np.random.choice(time_of_days,  N)
weather       = np.random.choice(weather_conds, N, p=[0.55, 0.20, 0.10, 0.15])

distance_km          = np.round(np.random.uniform(1, 100, N), 2)
avg_speed_kmph       = np.round(np.random.uniform(8, 95, N), 2)
traffic_level        = np.random.randint(1, 6, N)
ac_used              = np.random.randint(0, 2, N)
load_kg              = np.round(np.random.uniform(0, 600, N), 2)
engine_cc            = np.random.choice([100,150,800,1000,1200,1500,2000,2500], N)
tyre_pressure_ok     = np.random.randint(0, 2, N)
last_service_days    = np.random.randint(0, 400, N)
fuel_price_per_litre = np.round(np.random.uniform(88, 115, N), 2)
driver_hours_today   = np.round(np.random.uniform(0.5, 12, N), 1)  # NEW
idle_time_minutes    = np.round(np.random.uniform(0, 45, N), 1)    # NEW
harsh_braking_count  = np.random.randint(0, 15, N)                 # NEW
rpm_avg              = np.random.randint(800, 4000, N)             # NEW

# ─── Mileage Computation ──────────────────────────────────────────────────────
mileage_map = {'Bike': 48, 'Auto': 25, 'Car': 15, 'SUV': 10, 'Truck': 6}
base_mileage = np.array([mileage_map[v] for v in vehicle_type], dtype=float)

# Weather penalty
weather_penalty = np.where(weather == 'Rain', 1.5,
                  np.where(weather == 'Fog',  1.2,
                  np.where(weather == 'Hot',  1.0, 0.0)))

base_mileage -= traffic_level    * 1.3
base_mileage -= ac_used          * 2.2
base_mileage -= (load_kg / 180)
base_mileage += (avg_speed_kmph - 40) * 0.04
base_mileage += tyre_pressure_ok * 1.8
base_mileage -= (last_service_days / 90)
base_mileage -= weather_penalty
base_mileage -= (harsh_braking_count * 0.3)
base_mileage -= (idle_time_minutes * 0.05)
base_mileage  = np.clip(base_mileage, 3, 65)

noise = np.random.normal(0, 0.9, N)
fuel_consumed_litres = np.round((distance_km / base_mileage) + noise, 3)
fuel_consumed_litres = np.clip(fuel_consumed_litres, 0.1, 30)

# ─── Trip Cost ────────────────────────────────────────────────────────────────
trip_cost_inr = np.round(fuel_consumed_litres * fuel_price_per_litre, 2)

# ─── Carbon Emission ──────────────────────────────────────────────────────────
emission_factor = {'Petrol': 2.31, 'Diesel': 2.68, 'CNG': 1.96}
co2_factor = np.array([emission_factor[f] for f in fuel_type])
carbon_emission_kg = np.round(fuel_consumed_litres * co2_factor, 3)

# ─── Eco Score ────────────────────────────────────────────────────────────────
eco_score = (100
             - traffic_level        * 5
             - ac_used              * 8
             - (load_kg / 45)
             + tyre_pressure_ok     * 6
             - (last_service_days / 28)
             - (harsh_braking_count * 1.5)
             - (idle_time_minutes   * 0.4)
             + np.random.normal(0, 2.5, N))
eco_score = np.clip(np.round(eco_score, 1), 0, 100)

# ─── Trip Grade (NEW) ─────────────────────────────────────────────────────────
def grade(score):
    if score >= 85: return 'A'
    elif score >= 70: return 'B'
    elif score >= 55: return 'C'
    elif score >= 40: return 'D'
    else: return 'F'
trip_grade = np.array([grade(s) for s in eco_score])

# ─── Driver Fatigue Risk Score (NEW) ─────────────────────────────────────────
# Based on hours driven + night driving + harsh braking
time_penalty = np.where(time_of_day == 'Night', 20, 0)
fatigue_risk = np.clip(
    (driver_hours_today * 7) + time_penalty + (harsh_braking_count * 2)
    + np.random.normal(0, 3, N), 0, 100)
fatigue_risk = np.round(fatigue_risk, 1)

# ─── EV Equivalent Cost (NEW) ────────────────────────────────────────────────
# Avg EV electricity consumption: 15 kWh/100km; avg India electricity ₹8/kWh
ev_cost_per_trip = np.round((distance_km / 100) * 15 * 8, 2)

# ─── Anomaly Flag (NEW) ──────────────────────────────────────────────────────
# Trips with unusually high fuel relative to distance are anomalies
expected_fuel = distance_km / base_mileage
deviation = np.abs(fuel_consumed_litres - expected_fuel)
anomaly_flag = (deviation > 1.5).astype(int)

# ─── Build DataFrame ─────────────────────────────────────────────────────────
df = pd.DataFrame({
    'trip_id':               range(1, N + 1),
    'vehicle_type':          vehicle_type,
    'fuel_type':             fuel_type,
    'road_type':             road_type,
    'time_of_day':           time_of_day,
    'weather':               weather,
    'distance_km':           distance_km,
    'avg_speed_kmph':        avg_speed_kmph,
    'traffic_level':         traffic_level,
    'ac_used':               ac_used,
    'load_kg':               load_kg,
    'engine_cc':             engine_cc,
    'tyre_pressure_ok':      tyre_pressure_ok,
    'last_service_days':     last_service_days,
    'fuel_price_per_litre':  fuel_price_per_litre,
    'driver_hours_today':    driver_hours_today,
    'idle_time_minutes':     idle_time_minutes,
    'harsh_braking_count':   harsh_braking_count,
    'rpm_avg':               rpm_avg,
    'fuel_consumed_litres':  fuel_consumed_litres,
    'trip_cost_inr':         trip_cost_inr,
    'carbon_emission_kg':    carbon_emission_kg,
    'eco_score':             eco_score,
    'trip_grade':            trip_grade,
    'fatigue_risk':          fatigue_risk,
    'ev_cost_per_trip':      ev_cost_per_trip,
    'anomaly_flag':          anomaly_flag
})

os.makedirs('data', exist_ok=True)
df.to_csv('data/ecodriveiq_dataset.csv', index=False)
print(f"✅ Dataset created: {N} rows → data/ecodriveiq_dataset.csv")
print(df[['fuel_consumed_litres','trip_cost_inr','carbon_emission_kg',
          'eco_score','trip_grade','fatigue_risk','anomaly_flag']].head(8))