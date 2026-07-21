import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from typing import Any

MODEL_PATH = "models/anomaly_model.pkl"


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

    IMPORTANT: does NOT use a fixed score threshold. IsolationForest's raw
    score_samples() output shifts depending on the training data itself, so a
    hardcoded cutoff (e.g. -0.1) can end up flagging everything or nothing
    depending on dataset size/shape. Instead we rely on the model's own
    decision_function(), which is score_samples() minus an internal offset_
    computed from `contamination` — this self-adjusts to the data and is
    the same boundary model.predict() uses (< 0 = anomaly, respecting the
    configured contamination rate).
    """
    if len(events) < 5:
        raise ValueError("Need at least 5 events to train the anomaly model.")

    os.makedirs("models", exist_ok=True)

    df = extract_features(events)

    model = IsolationForest(
        n_estimators=100,   # number of trees in the forest
        contamination=0.1,  # expect ~10% anomalies
        random_state=42    # reproducibility
    )
    model.fit(df)          # Train the model

    joblib.dump(model, MODEL_PATH) # Save the trained model to disk

    # Score training data to show distribution (decision_function, not raw score_samples)
    decision_scores = model.decision_function(df)
    return {
        "events_trained_on": len(events),
        "model_path":        MODEL_PATH,
        "avg_score":         round(float(np.mean(decision_scores)), 4),
        "min_score":         round(float(np.min(decision_scores)), 4),
        "max_score":         round(float(np.max(decision_scores)), 4),
        "threshold":         0.0,  # decision_function boundary is always 0 by definition
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
    score = float(model.decision_function(df)[0])
    return round(score, 4), score < 0


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

    model  = joblib.load(MODEL_PATH)  # Load the trained IsolationForest model
    df     = extract_features(events)  # Extract features from the events
    scores = model.decision_function(df) # Calculate anomaly scores

    results = []
    for i, event in enumerate(events):
        score = round(float(scores[i]), 4)
        results.append({
            "id":            event["id"],
            "anomaly_score": score,
            "is_anomaly":    score < 0
        })

    return results