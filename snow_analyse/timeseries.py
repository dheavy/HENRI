import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def aggregate_incidents(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Aggregate incidents by delegation, region, alert_category, time."""
    result = {}

    df = df.copy()
    df["month"] = df["opened_dt"].dt.to_period("M")
    df["week"] = df["opened_dt"].dt.to_period("W")

    # By region and month
    if "region" in df.columns:
        result["region_monthly"] = (
            df.groupby(["region", "month"]).size().reset_index(name="count")
        )

    # By delegation and month
    result["delegation_monthly"] = (
        df[df["delegation_code"].notna()]
        .groupby(["delegation_code", "month"]).size().reset_index(name="count")
    )

    # By alert_category and month (prometheus only)
    prom = df[df["is_prometheus"]]
    if not prom.empty:
        result["category_monthly"] = (
            prom.groupby(["alert_category", "month"]).size().reset_index(name="count")
        )

    return result

def detect_anomalies(df: pd.DataFrame, group_col: str, threshold_sigma: float = 2.0) -> pd.DataFrame:
    """Flag periods where incident count exceeds mean + threshold*sigma for a group."""
    df = df.copy()
    df["month"] = df["opened_dt"].dt.to_period("M")

    counts = df.groupby([group_col, "month"]).size().reset_index(name="count")

    stats = counts.groupby(group_col)["count"].agg(["mean", "std"]).reset_index()
    stats.columns = [group_col, "mean_count", "std_count"]
    stats["std_count"] = stats["std_count"].fillna(0)

    merged = counts.merge(stats, on=group_col)
    merged["threshold"] = merged["mean_count"] + threshold_sigma * merged["std_count"]
    merged["is_anomaly"] = merged["count"] > merged["threshold"]

    return merged[merged["is_anomaly"]]
