"""
FastAPI Service for Flood Risk Prediction
Updated to work with new spatial features and 5 Indian cities
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import pandas as pd
import numpy as np
import joblib
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv('../node-backend/.env')

# Database connection
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', 5432),
    'database': os.getenv('DB_NAME', 'flood_risk_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD')
}

# Model paths
MODEL_PATH = '../artifacts/flood_risk_model.joblib'
METADATA_PATH = '../artifacts/model_metadata.json'

# Feature columns (must match training)
FEATURE_COLUMNS = [
    'rainfall_24h', 'rainfall_3d', 'rainfall_7d', 'rainfall_intensity',
    'api_index', 'month', 'is_monsoon_season',
    'latitude', 'longitude', 'rainfall_pct_of_seasonal_normal',
    'humidity', 'temp_max', 'temp_min', 'temp_mean'
]

# Risk level mappings
RISK_LEVELS = {0: 'low', 1: 'medium', 2: 'high'}
RISK_LABELS = {'low': 0, 'medium': 1, 'high': 2}

# Actions based on risk level
ACTIONS = {
    'low': 'Routine monitoring. No action required.',
    'medium': 'Pre-position relief stock, warn local officials, monitor gauges every 6h.',
    'high': 'Issue public warning, prepare evacuation of low-lying wards, activate control room.'
}

# Alert threshold for elevated risk (medium + high probability)
ALERT_THRESHOLD = 0.55


app = FastAPI(
    title="Flood Risk Prediction API",
    version="2.0.0",
    description="AI-driven flood risk prediction for Indian cities with spatial generalization"
)


class PredictionRequest(BaseModel):
    """Request model for single city prediction"""
    city: str = Field(..., description="City name (Mumbai, Chennai, Kolkata, Patna, Guwahati)")
    date: str = Field(..., description="Date for prediction (YYYY-MM-DD)")
    use_forecast: bool = Field(default=False, description="Use forecast data if available")


class BatchPredictionRequest(BaseModel):
    """Request model for batch predictions"""
    cities: List[str] = Field(..., description="List of city names")
    date: str = Field(..., description="Date for prediction (YYYY-MM-DD)")
    use_forecast: bool = Field(default=False, description="Use forecast data if available")


class FeatureBasedPredictionRequest(BaseModel):
    """Request model using raw feature values"""
    features: dict = Field(..., description="Dictionary of feature values matching FEATURE_COLUMNS")
    city: str = Field(..., description="City name for context")


class PredictionResponse(BaseModel):
    """Response model for predictions"""
    city: str
    date: str
    risk_level: str
    risk_score: float
    probabilities: dict
    should_alert: bool
    recommended_action: str
    contributing_factors: List[dict]
    model_version: str
    prediction_timestamp: str


def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG)


def load_model():
    """Load trained model and metadata"""
    if not os.path.exists(MODEL_PATH):
        raise HTTPException(status_code=503, detail="Model not found. Please train the model first.")
    
    model = joblib.load(MODEL_PATH)
    
    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, 'r') as f:
            metadata = json.load(f)
    else:
        metadata = {'model_version': 'unknown'}
    
    return model, metadata


def get_city_features(conn, city_name, target_date, use_forecast=False):
    """
    Fetch engineered features for a specific city and date
    """
    query = """
        SELECT 
            city_id, city_name, date,
            rainfall_24h, rainfall_3d, rainfall_7d, rainfall_intensity,
            api_index, month, is_monsoon_season,
            latitude, longitude, rainfall_pct_of_seasonal_normal,
            humidity, temp_max, temp_min, temp_mean
        FROM training_data
        WHERE city_name = %s AND date = %s
    """
    
    params = [city_name, target_date]
    df = pd.read_sql_query(query, conn, params=params)
    
    if df.empty and use_forecast:
        # Fallback to latest available data if forecast not implemented
        query = """
            SELECT 
                city_id, city_name, date,
                rainfall_24h, rainfall_3d, rainfall_7d, rainfall_intensity,
                api_index, month, is_monsoon_season,
                latitude, longitude, rainfall_pct_of_seasonal_normal,
                humidity, temp_max, temp_min, temp_mean
            FROM training_data
            WHERE city_name = %s
            ORDER BY date DESC
            LIMIT 1
        """
        df = pd.read_sql_query(query, conn, params=[city_name])
    
    return df


def prepare_features_for_prediction(features_dict):
    """
    Prepare feature array from dictionary
    """
    feature_array = []
    
    for col in FEATURE_COLUMNS:
        if col in features_dict:
            feature_array.append(features_dict[col])
        else:
            # Fill missing features with 0 or reasonable defaults
            if col in ['latitude', 'longitude']:
                feature_array.append(0.0)  # Will need actual coordinates
            elif col in ['month', 'is_monsoon_season']:
                feature_array.append(0)
            else:
                feature_array.append(0.0)
    
    return np.array([feature_array])


def make_prediction(model, features):
    """
    Make prediction using loaded model
    """
    # Ensure features are in correct shape
    if isinstance(features, dict):
        features = prepare_features_for_prediction(features)
    elif isinstance(features, pd.DataFrame):
        features = features[FEATURE_COLUMNS].values
    elif isinstance(features, list):
        features = np.array(features)
    
    # Get prediction and probabilities
    prediction = model.predict(features)[0]
    probabilities = model.predict_proba(features)[0]
    
    # Apply the same hybrid approach used during training
    # Combine model predictions with rainfall threshold rules for balanced performance
    high_risk_thresholds = {
        'rainfall_24h': 30.0,
        'rainfall_3d': 107.0,
        'rainfall_7d': 206.0,
        'api_index': 239.0
    }
    
    # Check if features meet high-risk rainfall thresholds
    high_risk_count = 0
    if 'rainfall_24h' in FEATURE_COLUMNS and 'rainfall_24h' in features:
        if features['rainfall_24h'] >= high_risk_thresholds['rainfall_24h']:
            high_risk_count += 1
    if 'rainfall_3d' in FEATURE_COLUMNS and 'rainfall_3d' in features:
        if features['rainfall_3d'] >= high_risk_thresholds['rainfall_3d']:
            high_risk_count += 1
    if 'rainfall_7d' in FEATURE_COLUMNS and 'rainfall_7d' in features:
        if features['rainfall_7d'] >= high_risk_thresholds['rainfall_7d']:
            high_risk_count += 1
    if 'api_index' in FEATURE_COLUMNS and 'api_index' in features:
        if features['api_index'] >= high_risk_thresholds['api_index']:
            high_risk_count += 1
    
    # Override model prediction if rainfall thresholds are met
    if high_risk_count >= 2:  # 2 criteria needed for balanced performance
        prediction = 2
    elif probabilities[2] > 0.3:  # Probability threshold
        prediction = 2
    
    return prediction, probabilities


def get_contributing_factors(model, features, feature_names=FEATURE_COLUMNS, top_n=5):
    """
    Get top contributing factors for the prediction
    """
    if hasattr(model, 'feature_importances_'):
        importances = model.feature_importances_
        
        # Get absolute feature values for this prediction
        if isinstance(features, np.ndarray):
            feature_values = features[0]
        elif isinstance(features, pd.DataFrame):
            feature_values = features.iloc[0].values
        else:
            feature_values = list(features.values())
        
        # Calculate contribution (importance * absolute feature value)
        contributions = []
        for i, (name, importance) in enumerate(zip(feature_names, importances)):
            if i < len(feature_values):
                contribution = abs(importance * feature_values[i])
                contributions.append({
                    'feature': name,
                    'importance': float(importance),
                    'value': float(feature_values[i]) if i < len(feature_values) else 0.0,
                    'contribution': float(contribution)
                })
        
        # Sort by contribution and return top N
        contributions.sort(key=lambda x: x['contribution'], reverse=True)
        return contributions[:top_n]
    
    return []


@app.get("/")
def root():
    """Root endpoint with API information"""
    return {
        "service": "Flood Risk Prediction API",
        "version": "2.0.0",
        "description": "AI-driven flood risk prediction for Indian cities",
        "endpoints": {
            "health": "/health",
            "predict": "/predict",
            "predict_batch": "/predict/batch",
            "predict_features": "/predict/features"
        },
        "supported_cities": ["Mumbai", "Chennai", "Kolkata", "Patna", "Guwahati"]
    }


@app.get("/health")
def health():
    """Health check endpoint"""
    try:
        model, metadata = load_model()
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_version": metadata.get('model_version', 'unknown'),
            "supported_cities": ["Mumbai", "Chennai", "Kolkata", "Patna", "Guwahati"]
        }
    except Exception as e:
        return {
            "status": "degraded",
            "model_loaded": False,
            "error": str(e)
        }


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    """
    Make flood risk prediction for a single city
    """
    try:
        # Load model
        model, metadata = load_model()
        
        # Connect to database
        conn = get_db_connection()
        
        # Get features for the city and date
        features_df = get_city_features(conn, request.city, request.date, request.use_forecast)
        
        if features_df.empty:
            conn.close()
            raise HTTPException(
                status_code=404,
                detail=f"No feature data found for {request.city} on {request.date}"
            )
        
        # Make prediction
        prediction, probabilities = make_prediction(model, features_df)
        
        # Get contributing factors
        contributing_factors = get_contributing_factors(model, features_df)
        
        # Calculate risk level and score
        risk_level = RISK_LEVELS[prediction]
        risk_score = float(0.5 * probabilities[1] + 1.0 * probabilities[2])  # Weighted score
        
        # Determine if alert should be triggered
        elevated_probability = float(probabilities[1] + probabilities[2])
        should_alert = elevated_probability >= ALERT_THRESHOLD or risk_level == 'high'
        
        # Prepare response
        response = {
            "city": request.city,
            "date": request.date,
            "risk_level": risk_level,
            "risk_score": round(risk_score, 4),
            "probabilities": {
                "low": round(float(probabilities[0]), 4),
                "medium": round(float(probabilities[1]), 4),
                "high": round(float(probabilities[2]), 4)
            },
            "should_alert": should_alert,
            "recommended_action": ACTIONS[risk_level],
            "contributing_factors": contributing_factors,
            "model_version": metadata.get('model_version', 'unknown'),
            "prediction_timestamp": datetime.now().isoformat()
        }
        
        conn.close()
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/batch")
def predict_batch(request: BatchPredictionRequest):
    """
    Make flood risk predictions for multiple cities
    """
    try:
        # Load model
        model, metadata = load_model()
        
        # Connect to database
        conn = get_db_connection()
        
        predictions = []
        errors = []
        
        for city in request.cities:
            try:
                # Get features for the city and date
                features_df = get_city_features(conn, city, request.date, request.use_forecast)
                
                if features_df.empty:
                    errors.append({
                        "city": city,
                        "error": f"No feature data found for {city} on {request.date}"
                    })
                    continue
                
                # Make prediction
                prediction, probabilities = make_prediction(model, features_df)
                
                # Calculate risk level and score
                risk_level = RISK_LEVELS[prediction]
                risk_score = float(0.5 * probabilities[1] + 1.0 * probabilities[2])
                
                # Determine if alert should be triggered
                elevated_probability = float(probabilities[1] + probabilities[2])
                should_alert = elevated_probability >= ALERT_THRESHOLD or risk_level == 'high'
                
                predictions.append({
                    "city": city,
                    "date": request.date,
                    "risk_level": risk_level,
                    "risk_score": round(risk_score, 4),
                    "probabilities": {
                        "low": round(float(probabilities[0]), 4),
                        "medium": round(float(probabilities[1]), 4),
                        "high": round(float(probabilities[2]), 4)
                    },
                    "should_alert": should_alert,
                    "recommended_action": ACTIONS[risk_level],
                    "model_version": metadata.get('model_version', 'unknown')
                })
                
            except Exception as e:
                errors.append({
                    "city": city,
                    "error": str(e)
                })
        
        conn.close()
        
        return {
            "predictions": predictions,
            "errors": errors,
            "total_requested": len(request.cities),
            "successful_predictions": len(predictions),
            "failed_predictions": len(errors)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/features")
def predict_features(request: FeatureBasedPredictionRequest):
    """
    Make prediction using raw feature values
    Useful for testing or when database features are not available
    """
    try:
        # Load model
        model, metadata = load_model()
        
        # Make prediction
        prediction, probabilities = make_prediction(model, request.features)
        
        # Calculate risk level and score
        risk_level = RISK_LEVELS[prediction]
        risk_score = float(0.5 * probabilities[1] + 1.0 * probabilities[2])
        
        # Determine if alert should be triggered
        elevated_probability = float(probabilities[1] + probabilities[2])
        should_alert = elevated_probability >= ALERT_THRESHOLD or risk_level == 'high'
        
        # Get contributing factors
        contributing_factors = get_contributing_factors(model, request.features)
        
        # Prepare response
        response = {
            "city": request.city,
            "risk_level": risk_level,
            "risk_score": round(risk_score, 4),
            "probabilities": {
                "low": round(float(probabilities[0]), 4),
                "medium": round(float(probabilities[1]), 4),
                "high": round(float(probabilities[2]), 4)
            },
            "should_alert": should_alert,
            "recommended_action": ACTIONS[risk_level],
            "contributing_factors": contributing_factors,
            "model_version": metadata.get('model_version', 'unknown'),
            "prediction_timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)  # Changed to 8003