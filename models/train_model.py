# models/train_model.py
# EcoDriveIQ v2.0 - Advanced Model Training
# CHANGED: Added fatigue_risk model, anomaly detection (IsolationForest),
#          new features (weather, time_of_day, harsh_braking, idle_time, rpm_avg)

import pandas as pd
import numpy as np
from sklearn.ensemble          import RandomForestRegressor, IsolationForest
from sklearn.model_selection   import train_test_split, cross_val_score
from sklearn.metrics           import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing     import LabelEncoder
import joblib
import os

print("📂 Loading dataset...")
df = pd.read_csv('data/ecodriveiq_dataset.csv')
print(f"   Shape: {df.shape}")

# ─── Encode Categoricals ──────────────────────────────────────────────────────
print("🔄 Encoding categorical columns...")
encoders = {}
for col in ['vehicle_type', 'fuel_type', 'road_type', 'time_of_day', 'weather']:
    le = LabelEncoder()
    df[f'{col}_enc'] = le.fit_transform(df[col])
    encoders[col] = le
    joblib.dump(le, f'models/le_{col}.pkl')
    print(f"   ✅ Encoded & saved: {col}")

# ─── Feature Set (EXPANDED) ──────────────────────────────────────────────────
FEATURES = [
    'vehicle_type_enc', 'fuel_type_enc', 'road_type_enc',
    'time_of_day_enc', 'weather_enc',
    'distance_km', 'avg_speed_kmph', 'traffic_level',
    'ac_used', 'load_kg', 'engine_cc', 'tyre_pressure_ok',
    'last_service_days', 'fuel_price_per_litre',
    'driver_hours_today', 'idle_time_minutes',
    'harsh_braking_count', 'rpm_avg'
]
joblib.dump(FEATURES, 'models/features.pkl')
print(f"\n📋 Feature count: {len(FEATURES)}")

X = df[FEATURES]

# ─── Regression Targets ───────────────────────────────────────────────────────
TARGETS = {
    'fuel':    'fuel_consumed_litres',
    'cost':    'trip_cost_inr',
    'carbon':  'carbon_emission_kg',
    'eco':     'eco_score',
    'fatigue': 'fatigue_risk'       # NEW
}

def evaluate(name, y_test, y_pred):
    mae  = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2   = r2_score(y_test, y_pred)
    bar  = '█' * int(r2 * 20)
    print(f"\n  📊 {name}")
    print(f"     MAE  = {mae:.4f}")
    print(f"     RMSE = {rmse:.4f}")
    print(f"     R²   = {r2:.4f}  {bar}")
    return r2

print("\n" + "="*55)
print("🤖 TRAINING REGRESSION MODELS")
print("="*55)

for key, target_col in TARGETS.items():
    y = df[target_col]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    evaluate(target_col, y_test, y_pred)

    path = f'models/{key}_model.pkl'
    joblib.dump(model, path)
    print(f"     💾 Saved → {path}")

# ─── Anomaly Detection (IsolationForest) NEW ─────────────────────────────────
print("\n" + "="*55)
print("🔍 TRAINING ANOMALY DETECTION MODEL")
print("="*55)

anomaly_features = [
    'distance_km', 'fuel_consumed_litres', 'avg_speed_kmph',
    'traffic_level', 'idle_time_minutes', 'harsh_braking_count'
]
X_anomaly = df[anomaly_features]

iso = IsolationForest(
    n_estimators=150,
    contamination=0.05,  # expect ~5% anomalous trips
    random_state=42,
    n_jobs=-1
)
iso.fit(X_anomaly)
joblib.dump(iso, 'models/anomaly_model.pkl')
joblib.dump(anomaly_features, 'models/anomaly_features.pkl')

# Validate
preds = iso.predict(X_anomaly)
n_anomalies = (preds == -1).sum()
print(f"   Anomalies detected in training set: {n_anomalies} / {len(df)}")
print(f"   ✅ Saved → models/anomaly_model.pkl")

# ─── Feature Importance ──────────────────────────────────────────────────────
print("\n" + "="*55)
print("📈 FEATURE IMPORTANCE (Fuel Model Top 8)")
print("="*55)
fuel_model   = joblib.load('models/fuel_model.pkl')
importances  = fuel_model.feature_importances_
feat_df      = pd.DataFrame({'feature': FEATURES, 'importance': importances})
feat_df      = feat_df.sort_values('importance', ascending=False).head(8)
for _, row in feat_df.iterrows():
    bar = '▓' * int(row['importance'] * 100)
    print(f"  {row['feature']:30s} {bar} {row['importance']:.4f}")

print("\n" + "="*55)
print("✅ ALL 5 MODELS TRAINED AND SAVED SUCCESSFULLY")
print("="*55)