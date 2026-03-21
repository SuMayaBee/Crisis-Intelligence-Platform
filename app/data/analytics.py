import numpy as np
import pandas as pd


def compute_changes(events: pd.DataFrame, window_hours: int) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["source", "current", "previous", "delta"])

    end_time = events["timestamp"].max()
    start_current = end_time - pd.Timedelta(hours=window_hours)
    start_previous = start_current - pd.Timedelta(hours=window_hours)

    current = events[(events["timestamp"] >= start_current) & (events["timestamp"] <= end_time)]
    previous = events[(events["timestamp"] >= start_previous) & (events["timestamp"] < start_current)]

    c = current.groupby("source").size().rename("current")
    p = previous.groupby("source").size().rename("previous")

    merged = pd.concat([c, p], axis=1).fillna(0)
    merged["current"] = merged["current"].astype(int)
    merged["previous"] = merged["previous"].astype(int)
    merged["delta"] = merged["current"] - merged["previous"]
    return merged.reset_index().sort_values("delta", ascending=False)


def compute_risk_by_region(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["region", "event_count", "avg_severity", "risk_score"])

    grouped = events.groupby("region").agg(
        event_count=("source", "size"),
        avg_severity=("severity", "mean"),
    )
    grouped["risk_score"] = (
        np.log1p(grouped["event_count"]) * 14 + grouped["avg_severity"] * 16
    ).round(2)
    return grouped.reset_index().sort_values("risk_score", ascending=False)
