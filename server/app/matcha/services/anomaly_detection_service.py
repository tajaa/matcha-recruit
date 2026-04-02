"""Anomaly Detection Service.

Statistical process control on time-series risk metrics.
Flags unusual spikes using rolling mean + standard deviation.

Requires >= 6 months of history data to produce meaningful results.
"""

import json
import logging
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

MIN_DATA_POINTS = 6  # Minimum months of history needed


@dataclass
class Anomaly:
    metric: str
    period: str  # ISO date of the data point
    value: float
    rolling_mean: float
    rolling_std: float
    z_score: float
    severity: str  # "warning" (2σ) or "alert" (3σ)
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TimeSeriesPoint:
    period: str
    value: float
    rolling_mean: float | None = None
    rolling_std: float | None = None
    z_score: float | None = None
    upper_2s: float | None = None  # mean + 2σ
    lower_2s: float | None = None  # mean - 2σ

    def to_dict(self) -> dict[str, Any]:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in asdict(self).items()}


@dataclass
class MetricTimeSeries:
    metric: str
    label: str
    data_points: int
    current_value: float
    rolling_mean: float
    rolling_std: float
    anomalies: list[Anomaly]
    time_series: list[TimeSeriesPoint] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["anomalies"] = [a.to_dict() for a in self.anomalies]
        d.pop("time_series", None)
        if self.time_series:
            d["time_series"] = [p.to_dict() for p in self.time_series]
        return d


@dataclass
class AnomalyDetectionResult:
    has_sufficient_data: bool
    data_points_available: int
    metrics: list[MetricTimeSeries]
    total_anomalies: int
    alert_count: int
    warning_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_sufficient_data": self.has_sufficient_data,
            "data_points_available": self.data_points_available,
            "metrics": [m.to_dict() for m in self.metrics],
            "total_anomalies": self.total_anomalies,
            "alert_count": self.alert_count,
            "warning_count": self.warning_count,
        }


def _detect_anomalies_in_series(
    metric: str,
    label: str,
    values: list[tuple[str, float]],
    window: int = 12,
) -> MetricTimeSeries:
    """Apply rolling mean + σ anomaly detection to a time series.

    Args:
        metric: Metric identifier.
        label: Human-readable label.
        values: List of (period_iso, value) tuples, chronologically ordered.
        window: Rolling window size in data points (default 12 for months).

    Returns:
        MetricTimeSeries with detected anomalies.
    """
    anomalies: list[Anomaly] = []
    ts_points: list[TimeSeriesPoint] = []

    if len(values) < MIN_DATA_POINTS:
        ts_points = [TimeSeriesPoint(period=v[0], value=round(v[1], 2)) for v in values]
        return MetricTimeSeries(
            metric=metric,
            label=label,
            data_points=len(values),
            current_value=values[-1][1] if values else 0.0,
            rolling_mean=0.0,
            rolling_std=0.0,
            anomalies=[],
            time_series=ts_points,
        )

    # Record early points without rolling stats
    for i in range(min(MIN_DATA_POINTS, len(values))):
        ts_points.append(TimeSeriesPoint(period=values[i][0], value=round(values[i][1], 2)))

    # Compute rolling statistics and check each point
    for i in range(MIN_DATA_POINTS, len(values)):
        # Use preceding points as the baseline window
        start = max(0, i - window)
        window_values = [v[1] for v in values[start:i]]

        if len(window_values) < 3:
            ts_points.append(TimeSeriesPoint(period=values[i][0], value=round(values[i][1], 2)))
            continue

        mean = sum(window_values) / len(window_values)
        variance = sum((v - mean) ** 2 for v in window_values) / len(window_values)
        std = math.sqrt(variance) if variance > 0 else 0.0

        period, current_val = values[i]
        z = (current_val - mean) / std if std > 0 else None

        ts_points.append(TimeSeriesPoint(
            period=period,
            value=round(current_val, 2),
            rolling_mean=round(mean, 2),
            rolling_std=round(std, 2),
            z_score=round(z, 2) if z is not None else None,
            upper_2s=round(mean + 2 * std, 2) if std > 0 else None,
            lower_2s=round(mean - 2 * std, 2) if std > 0 else None,
        ))

        if std == 0 or z is None:
            continue

        if abs(z) >= 3.0:
            severity = "alert"
        elif abs(z) >= 2.0:
            severity = "warning"
        else:
            continue

        direction = "above" if z > 0 else "below"
        anomalies.append(Anomaly(
            metric=metric,
            period=period,
            value=round(current_val, 2),
            rolling_mean=round(mean, 2),
            rolling_std=round(std, 2),
            z_score=round(z, 2),
            severity=severity,
            description=f"{label} jumped {abs(z):.1f}σ {direction} {window}-month average",
        ))

    # Current state (most recent window)
    recent_vals = [v[1] for v in values[-min(window, len(values)):]]
    current_mean = sum(recent_vals) / len(recent_vals) if recent_vals else 0.0
    current_var = sum((v - current_mean) ** 2 for v in recent_vals) / len(recent_vals) if recent_vals else 0.0
    current_std = math.sqrt(current_var) if current_var > 0 else 0.0

    return MetricTimeSeries(
        metric=metric,
        label=label,
        data_points=len(values),
        current_value=round(values[-1][1], 2) if values else 0.0,
        rolling_mean=round(current_mean, 2),
        rolling_std=round(current_std, 2),
        anomalies=anomalies,
        time_series=ts_points,
    )


async def detect_anomalies(
    company_id: UUID,
    months: int = 24,
) -> AnomalyDetectionResult:
    """Run anomaly detection across risk metrics for a company.

    Uses risk_assessment_history for dimension scores and
    ir_incidents / er_cases timestamps for event-based metrics.

    Args:
        company_id: Company to analyze.
        months: How many months of history to analyze (default 24).

    Returns:
        AnomalyDetectionResult with all detected anomalies.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)

    async with get_connection() as conn:
        # 1. Risk assessment history (monthly snapshots)
        history_rows = await conn.fetch(
            """
            SELECT overall_score, dimensions, computed_at
            FROM risk_assessment_history
            WHERE company_id = $1 AND computed_at >= $2
            ORDER BY computed_at ASC
            """,
            company_id,
            cutoff,
        )

        # 2. Monthly incident counts
        incident_rows = await conn.fetch(
            """
            SELECT date_trunc('month', created_at) AS month,
                   COUNT(*) AS cnt
            FROM ir_incidents
            WHERE company_id = $1 AND created_at >= $2
            GROUP BY date_trunc('month', created_at)
            ORDER BY month ASC
            """,
            company_id,
            cutoff,
        )

        # 3. Monthly ER case counts
        er_rows = await conn.fetch(
            """
            SELECT date_trunc('month', created_at) AS month,
                   COUNT(*) AS cnt
            FROM er_cases
            WHERE company_id = $1 AND created_at >= $2
            GROUP BY date_trunc('month', created_at)
            ORDER BY month ASC
            """,
            company_id,
            cutoff,
        )

        # 4. Monthly employee turnover (terminations)
        turnover_rows = await conn.fetch(
            """
            SELECT date_trunc('month', termination_date) AS month,
                   COUNT(*) AS cnt
            FROM employees
            WHERE org_id = $1
              AND termination_date IS NOT NULL
              AND termination_date >= $2
            GROUP BY date_trunc('month', termination_date)
            ORDER BY month ASC
            """,
            company_id,
            cutoff,
        )

    # Build time series
    all_metrics: list[MetricTimeSeries] = []
    total_data_points = 0

    # Overall score series
    overall_series: list[tuple[str, float]] = []
    compliance_series: list[tuple[str, float]] = []
    incidents_series: list[tuple[str, float]] = []
    er_series: list[tuple[str, float]] = []

    for row in history_rows:
        period = row["computed_at"].strftime("%Y-%m")
        overall_series.append((period, float(row["overall_score"])))

        dims = row["dimensions"]
        if isinstance(dims, str):
            dims = json.loads(dims)
        if isinstance(dims, dict):
            if "compliance" in dims:
                score = dims["compliance"].get("score", 0) if isinstance(dims["compliance"], dict) else 0
                compliance_series.append((period, float(score)))
            if "incidents" in dims:
                score = dims["incidents"].get("score", 0) if isinstance(dims["incidents"], dict) else 0
                incidents_series.append((period, float(score)))
            if "er_cases" in dims:
                score = dims["er_cases"].get("score", 0) if isinstance(dims["er_cases"], dict) else 0
                er_series.append((period, float(score)))

    total_data_points = max(
        len(overall_series),
        len(incident_rows),
        len(er_rows),
        len(turnover_rows),
    )

    if overall_series:
        all_metrics.append(_detect_anomalies_in_series(
            "overall_score", "Overall Risk Score", overall_series,
        ))
    if compliance_series:
        all_metrics.append(_detect_anomalies_in_series(
            "compliance_score", "Compliance Score", compliance_series,
        ))
    if incidents_series:
        all_metrics.append(_detect_anomalies_in_series(
            "incidents_score", "Incidents Score", incidents_series,
        ))
    if er_series:
        all_metrics.append(_detect_anomalies_in_series(
            "er_cases_score", "ER Cases Score", er_series,
        ))

    # Incident count series
    incident_series = [
        (row["month"].strftime("%Y-%m"), float(row["cnt"]))
        for row in incident_rows
    ]
    if incident_series:
        all_metrics.append(_detect_anomalies_in_series(
            "incident_count", "Monthly Incident Count", incident_series,
        ))

    # ER case count series
    er_case_series = [
        (row["month"].strftime("%Y-%m"), float(row["cnt"]))
        for row in er_rows
    ]
    if er_case_series:
        all_metrics.append(_detect_anomalies_in_series(
            "er_case_count", "Monthly ER Case Count", er_case_series,
        ))

    # Turnover series
    turnover_series = [
        (row["month"].strftime("%Y-%m"), float(row["cnt"]))
        for row in turnover_rows
    ]
    if turnover_series:
        all_metrics.append(_detect_anomalies_in_series(
            "turnover_count", "Monthly Turnover", turnover_series,
        ))

    # Aggregate anomaly counts
    total_anomalies = sum(len(m.anomalies) for m in all_metrics)
    alert_count = sum(
        1 for m in all_metrics for a in m.anomalies if a.severity == "alert"
    )
    warning_count = sum(
        1 for m in all_metrics for a in m.anomalies if a.severity == "warning"
    )

    return AnomalyDetectionResult(
        has_sufficient_data=total_data_points >= MIN_DATA_POINTS,
        data_points_available=total_data_points,
        metrics=all_metrics,
        total_anomalies=total_anomalies,
        alert_count=alert_count,
        warning_count=warning_count,
    )
