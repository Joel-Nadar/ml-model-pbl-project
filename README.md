# Flood Risk Prediction System - AI-Driven Climate Resilience Platform

## Overview
This is a comprehensive flood risk prediction system for 5 major Indian cities (Mumbai, Chennai, Kolkata, Patna, Guwahati) using machine learning with spatial generalization capabilities.

## Architecture
- **Node.js Backend**: Data ingestion, scheduling, alert system
- **Python ML Service**: XGBoost model training and FastAPI inference
- **PostgreSQL + PostGIS**: Data storage and spatial queries
- **Open-Meteo API**: Live and historical weather data

## Project Structure
```
PBL PROJECT/
├── node-backend/          # Node.js backend services
│   ├── src/
│   │   ├── config/       # Database and city configurations
│   │   └── scripts/      # Data ingestion and cron jobs
│   ├── database/         # SQL schema
│   └── package.json
├── python-ml/            # Python ML services
│   ├── feature_engineering.py
│   ├── train_model.py
│   ├── fastapi_service.py
│   └── requirements.txt
├── data/                 # Data files
│   └── flood_events_template.csv
└── climate-ml/           # Original synthetic data project
```

## Prerequisites
- Node.js 18+
- Python 3.9+
- PostgreSQL 14+ with PostGIS extension
- Open-Meteo API (free, no key required)

## Setup Instructions

### 1. Database Setup
```bash
# Create PostgreSQL database
createdb flood_risk_db

# Run schema creation
cd node-backend
psql -d flood_risk_db -f database/schema.sql
```

### 2. Environment Configuration
```bash
cd node-backend
cp .env.example .env
# Edit .env with your database credentials and API keys
```

### 3. Install Dependencies
```bash
# Node.js dependencies
cd node-backend
npm install

# Python dependencies
cd ../python-ml
pip install -r requirements.txt
```

### 4. Data Ingestion
```bash
cd node-backend

# Load flood events data
node src/scripts/loadFloodEvents.js

# Ingest historical weather data (may take time)
node src/scripts/ingestHistoricalWeather.js
```

### 5. Feature Engineering
```bash
cd python-ml
python feature_engineering.py
```

### 6. Model Training
```bash
python train_model.py
```

### 7. Start ML Service
```bash
python fastapi_service.py
# Service runs on http://localhost:8001
```

### 8. Start Daily Cron Job
```bash
cd ../node-backend
node src/scripts/dailyCron.js --schedule
```

## API Endpoints

### Health Check
```
GET http://localhost:8001/health
```

### Single City Prediction
```
POST http://localhost:8001/predict
{
  "city": "Mumbai",
  "date": "2024-09-25",
  "use_forecast": true
}
```

### Batch Prediction
```
POST http://localhost:8001/predict/batch
{
  "cities": ["Mumbai", "Chennai", "Kolkata"],
  "date": "2024-09-25",
  "use_forecast": true
}
```

### Feature-Based Prediction
```
POST http://localhost:8001/predict/features
{
  "city": "Mumbai",
  "features": {
    "rainfall_24h": 45.2,
    "rainfall_3d": 120.5,
    "rainfall_7d": 250.8,
    "rainfall_intensity": 15.3,
    "api_index": 180.5,
    "month": 9,
    "is_monsoon_season": 1,
    "latitude": 19.0760,
    "longitude": 72.8777,
    "rainfall_pct_of_seasonal_normal": 85.5,
    "humidity": 85.0,
    "temp_max": 32.0,
    "temp_min": 25.0,
    "temp_mean": 28.5
  }
}
```

## Target Cities
- **Mumbai**: 19.0760, 72.8777 (Population: 12.4M)
- **Chennai**: 13.0827, 80.2707 (Population: 7.0M)  
- **Kolkata**: 22.5726, 88.3639 (Population: 4.5M)
- **Patna**: 25.5941, 85.1376 (Population: 2.1M)
- **Guwahati**: 26.1445, 91.7362 (Population: 0.97M)

## Model Features
- **Rainfall Features**: 24h, 3d, 7d rolling sums, intensity
- **API Index**: Antecedent Precipitation Index for soil saturation
- **Seasonal Features**: Month, monsoon season flags
- **Spatial Features**: Latitude, longitude for generalization
- **Normal Comparison**: Rainfall as % of seasonal normal
- **Weather**: Humidity, temperature metrics

## Model Performance
- **Algorithm**: XGBoost with spatial features
- **Training**: Time-based split (prevents data leakage)
- **Objective**: Maximize recall for high-risk class
- **Generalization**: Single model for all cities (scales to new locations)

## Alert System
- **SMS Alerts**: Via Twilio for high-risk predictions
- **Email Alerts**: Via SMTP for detailed notifications
- **Thresholds**: Configurable risk thresholds
- **Recipients**: Multiple phone numbers and email addresses

## Monitoring
- **Prediction Logging**: All predictions logged to database
- **Accuracy Tracking**: Compare predictions vs actual outcomes
- **Drift Detection**: Monitor model performance over time
- **Feature Importance**: Track which features drive predictions

## Key Features
✅ **Spatial Generalization**: Model learns patterns, not city-specific thresholds
✅ **Real-time Data**: Daily weather data ingestion from Open-Meteo
✅ **Time-based Validation**: Prevents future data leakage
✅ **Safety-first**: High recall for dangerous flood conditions
✅ **Interpretable**: Feature importance analysis for domain experts
✅ **Scalable**: Add new cities without code changes (just coordinates)

## Development Notes
- **Data Sources**: Open-Meteo (primary), NASA POWER (fallback)
- **Ground Truth**: Manual flood event compilation from CWC/NDMA
- **API Index**: Standard hydrological formula with k=0.90 decay
- **Monsoon Handling**: City-specific monsoon periods
- **Alert Logic**: High risk + threshold-based triggering

## Future Enhancements
- Real-time satellite data integration
- River gauge data from CWC
- Social media sentiment analysis
- Mobile app for public alerts
- Dashboard for visualization
- More cities and regions

## License
MIT License - see LICENSE file for details

## Acknowledgments
- Open-Meteo API for weather data
- Central Water Commission (CWC) for river data
- National Disaster Management Authority (NDMA) for flood records