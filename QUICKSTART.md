# Quick Start Guide - Flood Risk Prediction System

## Prerequisites
- Node.js 18+, Python 3.9+, PostgreSQL 14+ with PostGIS
- Internet connection for Open-Meteo API access

## Fast Setup (5 minutes)

### 1. Run Setup Script
**Windows:**
```bash
setup.bat
```

**Linux/Mac:**
```bash
chmod +x setup.sh
./setup.sh
```

### 2. Configure Alerts (Optional)
Edit `node-backend/.env` to add:
```bash
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=your_number
ALERT_PHONE_NUMBERS=+919876543210,+919876543211
ALERT_EMAILS=admin@example.com
```

### 3. Ingest Historical Data (10-30 minutes)
```bash
cd node-backend
node src/scripts/ingestHistoricalWeather.js
```

### 4. Engineer Features (2 minutes)
```bash
cd ../python-ml
python feature_engineering.py
```

### 5. Train Model (5 minutes)
```bash
python train_model.py
```

### 6. Start Services
**Terminal 1 - ML Service:**
```bash
python fastapi_service.py
```

**Terminal 2 - Cron Job:**
```bash
cd ../node-backend
node src/scripts/dailyCron.js --schedule
```

## Test the API

### Health Check
```bash
curl http://localhost:8001/health
```

### Single City Prediction
```bash
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Mumbai",
    "date": "2024-09-25",
    "use_forecast": true
  }'
```

### Batch Prediction
```bash
curl -X POST http://localhost:8001/predict/batch \
  -H "Content-Type: application/json" \
  -d '{
    "cities": ["Mumbai", "Chennai", "Kolkata"],
    "date": "2024-09-25",
    "use_forecast": true
  }'
```

## Manual Testing with Features

If you don't have historical data yet, test with raw features:

```bash
curl -X POST http://localhost:8001/predict/features \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

## Expected Response

```json
{
  "city": "Mumbai",
  "date": "2024-09-25",
  "risk_level": "medium",
  "risk_score": 0.6549,
  "probabilities": {
    "low": 0.0048,
    "medium": 0.6807,
    "high": 0.3145
  },
  "should_alert": true,
  "recommended_action": "Pre-position relief stock, warn local officials, monitor gauges every 6h.",
  "contributing_factors": [
    {
      "feature": "rainfall_3d",
      "importance": 0.25,
      "value": 120.5,
      "contribution": 30.12
    }
  ],
  "model_version": "2024.09.25-1430",
  "prediction_timestamp": "2024-09-25T14:30:00.000Z"
}
```

## Troubleshooting

### Database Connection Error
- Check PostgreSQL is running: `pg_isready`
- Verify credentials in `node-backend/.env`
- Ensure database exists: `psql -l`

### Module Not Found Errors
- Reinstall dependencies: `npm install` and `pip install -r requirements.txt`

### Open-Meteo API Errors
- Check internet connection
- API is free and doesn't require authentication
- Try again later (rate limits may apply)

### Model Not Found Error
- Ensure you ran `python train_model.py`
- Check model file exists: `ls artifacts/flood_risk_model.joblib`

## Architecture Overview

```
┌─────────────────┐
│  Open-Meteo API │ (Weather Data)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Node.js Backend│ (Data Ingestion + Scheduling)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   PostgreSQL    │ (Data Storage)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Python ML Service│ (Feature Engineering + Training + Inference)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Alert System   │ (Twilio SMS + Email)
└─────────────────┘
```

## Key Features Delivered

✅ **5 Indian Cities**: Mumbai, Chennai, Kolkata, Patna, Guwahati
✅ **Real-time Data**: Open-Meteo API integration  
✅ **Spatial Generalization**: Single model scales to new cities
✅ **Advanced Features**: API index, rolling rainfall, seasonal normals
✅ **Time-based Validation**: Prevents data leakage
✅ **Safety-first**: High recall for dangerous conditions
✅ **Alert System**: SMS and email notifications
✅ **Monitoring**: Prediction logging and drift detection
✅ **Scalable**: Add new cities without code changes

## Next Steps for Production

1. **Add More Historical Data**: Extend historical weather ingestion
2. **Refine Flood Events**: Add more ground truth flood records
3. **Tune Model**: Adjust thresholds based on domain expert feedback
4. **Add River Data**: Integrate CWC river gauge data
5. **Create Dashboard**: Build visualization interface
6. **Mobile App**: Public-facing alert application
7. **Expand Cities**: Add more locations across India

## Support

For issues or questions:
- Check logs: `node-backend/logs/cron-job.log`
- API docs: `http://localhost:8001/docs`
- Database: `psql -d flood_risk_db`

## License

MIT License - Free for commercial and research use