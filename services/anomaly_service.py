import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from typing import Any

MODEL_PATH = "models/anomaly_model.pkl"
ANOMALY_THRESHOLD = -0.1  # scores below this = anomaly


# ── Feature extraction ─────────────────────────────────────
def extract_features(events: list[dict]) -> pd.DataFrame:
    """
    Extract numeric features from event JSONB payloads for IsolationForest.
    All features must be numeric — strings are encoded or dropped.
    """
    rows = []
    for e in events:
        payload = e.get("payload", {}) or {}

        # Encode event_type as integer
        event_type_map = {
            "login":     0,
            "logout":    1,
            "purchase":  2,
            "page_view": 3
        }
        event_type_num = event_type_map.get(e.get("event_type", ""), 4)

        # Status: failed=1, success=0, unknown=0
        status = payload.get("status", "")
        status_num = 1 if status == "failed" else 0

        # Amount (purchases) — 0 for non-purchases
        amount = float(payload.get("amount", 0) or 0)

        # Page duration (page_views) — 0 for others
        duration = float(payload.get("duration_ms", 0) or 0)

        # Country encoding — IN=0, US=1, UK=2, other=3
        country_map = {"IN": 0, "US": 1, "UK": 2}
        country_num = country_map.get(payload.get("country", ""), 3)

        # Device encoding — mobile=0, desktop=1, tablet=2, other=3
        device_map = {"mobile": 0, "desktop": 1, "tablet": 2}
        device_num = device_map.get(payload.get("device", ""), 3)

        rows.append({
            "event_type":  event_type_num,
            "status":      status_num,
            "amount":      amount,
            "duration_ms": duration,
            "country":     country_num,
            "device":      device_num,
        })

    return pd.DataFrame(rows)


# ── Train ──────────────────────────────────────────────────
def train_model(events: list[dict]) -> dict:
    """
    Train IsolationForest on existing events.
    Saves model to disk as models/anomaly_model.pkl.
    Returns training summary.
    """
    if len(events) < 5:
        raise ValueError("Need at least 5 events to train the anomaly model.")

    os.makedirs("models", exist_ok=True)

    df = extract_features(events)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.1,  # expect ~10% anomalies
        random_state=42
    )
    model.fit(df)

    joblib.dump(model, MODEL_PATH)

    # Score training data to show distribution
    scores = model.score_samples(df)
    return {
        "events_trained_on": len(events),
        "model_path":        MODEL_PATH,
        "avg_score":         round(float(np.mean(scores)), 4),
        "min_score":         round(float(np.min(scores)), 4),
        "max_score":         round(float(np.max(scores)), 4),
        "threshold":         ANOMALY_THRESHOLD,
    }


# ── Score single event ─────────────────────────────────────
def score_event(event: dict) -> tuple[float, bool]:
    """
    Score a single event using the saved model.
    Returns (anomaly_score, is_anomaly).
    Falls back gracefully if model not trained yet.
    """
    if not os.path.exists(MODEL_PATH):
        return 0.0, False

    model = joblib.load(MODEL_PATH)
    df    = extract_features([event])
    score = float(model.score_samples(df)[0])
    return round(score, 4), score < ANOMALY_THRESHOLD


# ── Score all events ───────────────────────────────────────
def score_all_events(events: list[dict]) -> list[dict]:
    """
    Score a batch of events using the saved model.
    Returns list of {id, anomaly_score, is_anomaly}.
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError("Model not trained yet. Call POST /events/ai/anomaly/train first.")

    if not events:
        return []

    model  = joblib.load(MODEL_PATH)
    df     = extract_features(events)
    scores = model.score_samples(df)

    results = []
    for i, event in enumerate(events):
        score = round(float(scores[i]), 4)
        results.append({
            "id":            event["id"],
            "anomaly_score": score,
            "is_anomaly":    score < ANOMALY_THRESHOLD
        })

    return results
