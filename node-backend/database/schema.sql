-- Flood Risk Prediction Database Schema
-- PostgreSQL + PostGIS for spatial data

-- Enable PostGIS extension for spatial queries
CREATE EXTENSION IF NOT EXISTS postgis;

-- Cities table with spatial coordinates
CREATE TABLE IF NOT EXISTS cities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    population BIGINT,
    geom GEOMETRY(POINT, 4326),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create spatial index on cities
CREATE INDEX IF NOT EXISTS idx_cities_geom ON cities USING GIST (geom);

-- Weather daily data from Open-Meteo API
CREATE TABLE IF NOT EXISTS weather_daily (
    id SERIAL PRIMARY KEY,
    city_id INTEGER REFERENCES cities(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    rainfall_mm DECIMAL(10, 2),
    rainfall_hours DECIMAL(10, 2),
    humidity DECIMAL(5, 2),
    temp_max DECIMAL(5, 2),
    temp_min DECIMAL(5, 2),
    temp_mean DECIMAL(5, 2),
    data_source VARCHAR(50) DEFAULT 'open-meteo',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(city_id, date)
);

-- Create indexes for weather queries
CREATE INDEX IF NOT EXISTS idx_weather_city_date ON weather_daily(city_id, date);
CREATE INDEX IF NOT EXISTS idx_weather_date ON weather_daily(date);

-- Manual flood event records (ground truth for labeling)
CREATE TABLE IF NOT EXISTS flood_events (
    id SERIAL PRIMARY KEY,
    city_id INTEGER REFERENCES cities(id) ON DELETE CASCADE,
    event_date DATE NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    description TEXT,
    source VARCHAR(100), -- CWC, NDMA, news archive, etc.
    affected_population INTEGER,
    economic_loss_usd DECIMAL(15, 2),
    casualties INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(city_id, event_date)
);

-- Create index for flood event queries
CREATE INDEX IF NOT EXISTS idx_flood_events_city_date ON flood_events(city_id, event_date);

-- Training data table (joined weather + flood labels)
CREATE TABLE IF NOT EXISTS training_data (
    id SERIAL PRIMARY KEY,
    city_id INTEGER REFERENCES cities(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    -- Raw weather features
    rainfall_mm DECIMAL(10, 2),
    rainfall_hours DECIMAL(10, 2),
    humidity DECIMAL(5, 2),
    temp_max DECIMAL(5, 2),
    temp_min DECIMAL(5, 2),
    temp_mean DECIMAL(5, 2),
    -- Engineered features
    rainfall_24h DECIMAL(10, 2),
    rainfall_3d DECIMAL(10, 2),
    rainfall_7d DECIMAL(10, 2),
    rainfall_intensity DECIMAL(10, 2),
    api_index DECIMAL(10, 2), -- Antecedent Precipitation Index
    month INTEGER,
    is_monsoon_season INTEGER,
    latitude DECIMAL(10, 7),
    longitude DECIMAL(10, 7),
    rainfall_pct_of_seasonal_normal DECIMAL(10, 2),
    -- Label
    risk_level INTEGER CHECK (risk_level IN (0, 1, 2)), -- 0=low, 1=medium, 2=high
    risk_label VARCHAR(20),
    -- Metadata
    data_source VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(city_id, date)
);

-- Create indexes for training data queries
CREATE INDEX IF NOT EXISTS idx_training_city_date ON training_data(city_id, date);
CREATE INDEX IF NOT EXISTS idx_training_risk_level ON training_data(risk_level);
CREATE INDEX IF NOT EXISTS idx_training_monsoon ON training_data(is_monsoon_season);

-- Predictions log for monitoring and drift detection
CREATE TABLE IF NOT EXISTS predictions_log (
    id SERIAL PRIMARY KEY,
    city_id INTEGER REFERENCES cities(id) ON DELETE CASCADE,
    prediction_date TIMESTAMP NOT NULL,
    target_date DATE NOT NULL,
    predicted_risk_level INTEGER CHECK (predicted_risk_level IN (0, 1, 2)),
    predicted_risk_label VARCHAR(20),
    risk_score DECIMAL(5, 4),
    features_used JSONB,
    model_version VARCHAR(50),
    was_alert_triggered BOOLEAN DEFAULT FALSE,
    actual_outcome INTEGER CHECK (actual_outcome IN (0, 1, 2)), -- Filled in later for accuracy tracking
    actual_outcome_label VARCHAR(20),
    outcome_date TIMESTAMP, -- When actual outcome was determined
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for prediction log queries
CREATE INDEX IF NOT EXISTS idx_predictions_city_date ON predictions_log(city_id, prediction_date);
CREATE INDEX IF NOT EXISTS idx_predictions_target_date ON predictions_log(target_date);
CREATE INDEX IF NOT EXISTS idx_predictions_outcome ON predictions_log(actual_outcome) WHERE actual_outcome IS NOT NULL;

-- Model performance metrics for drift monitoring
CREATE TABLE IF NOT EXISTS model_performance (
    id SERIAL PRIMARY KEY,
    city_id INTEGER REFERENCES cities(id) ON DELETE CASCADE,
    evaluation_date DATE NOT NULL,
    time_period VARCHAR(50), -- 'last_7_days', 'last_30_days', 'monsoon_2024', etc.
    precision_high DECIMAL(5, 4),
    recall_high DECIMAL(5, 4),
    f1_high DECIMAL(5, 4),
    precision_overall DECIMAL(5, 4),
    recall_overall DECIMAL(5, 4),
    f1_overall DECIMAL(5, 4),
    total_predictions INTEGER,
    correct_predictions INTEGER,
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(city_id, evaluation_date, time_period)
);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers for updated_at
CREATE TRIGGER update_cities_updated_at BEFORE UPDATE ON cities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_weather_daily_updated_at BEFORE UPDATE ON weather_daily
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_flood_events_updated_at BEFORE UPDATE ON flood_events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert the 5 target Indian cities
INSERT INTO cities (name, latitude, longitude, population, geom) VALUES
('Mumbai', 19.0760, 72.8777, 12440000, ST_SetSRID(ST_MakePoint(72.8777, 19.0760), 4326)),
('Chennai', 13.0827, 80.2707, 7046000, ST_SetSRID(ST_MakePoint(80.2707, 13.0827), 4326)),
('Kolkata', 22.5726, 88.3639, 4497000, ST_SetSRID(ST_MakePoint(88.3639, 22.5726), 4326)),
('Patna', 25.5941, 85.1376, 2094000, ST_SetSRID(ST_MakePoint(85.1376, 25.5941), 4326)),
('Guwahati', 26.1445, 91.7362, 967000, ST_SetSRID(ST_MakePoint(91.7362, 26.1445), 4326))
ON CONFLICT (name) DO NOTHING;