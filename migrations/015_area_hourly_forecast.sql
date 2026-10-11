-- V2 hourly congestion forecasts are area-level, not tourist-site ground truth.
-- Never mix official CityData forecasts with our own validated model predictions.
CREATE TABLE IF NOT EXISTS area_hourly_forecast (
    area_cd text NOT NULL,
    forecast_at timestamptz NOT NULL,
    issued_at timestamptz NOT NULL,
    congestion_label smallint NOT NULL CHECK (congestion_label BETWEEN 0 AND 3),
    congestion_level text NOT NULL,
    horizon_hours smallint NOT NULL CHECK (horizon_hours BETWEEN 1 AND 12),
    model_version text NOT NULL,
    validation_balanced_accuracy double precision NOT NULL,
    validation_baseline_accuracy double precision NOT NULL,
    PRIMARY KEY (area_cd, forecast_at)
);
CREATE INDEX IF NOT EXISTS area_hourly_forecast_issue_idx
 ON area_hourly_forecast(area_cd, issued_at DESC, forecast_at);
