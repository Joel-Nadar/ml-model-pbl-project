"""
Feature Engineering Script for Flood Risk Prediction
Computes engineered features including API (Antecedent Precipitation Index)
and other hydrological features for training and inference.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
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

# API index decay constant (k in the formula)
API_DECAY_CONSTANT = 0.90

# City-specific configurations (monsoon months and seasonal averages)
CITY_CONFIG = {
    'Mumbai': {
        'monsoon_months': [6, 7, 8, 9],
        'seasonal_avg_rainfall': 2400  # mm during monsoon season
    },
    'Chennai': {
        'monsoon_months': [10, 11, 12],
        'seasonal_avg_rainfall': 1200
    },
    'Kolkata': {
        'monsoon_months': [6, 7, 8, 9],
        'seasonal_avg_rainfall': 1600
    },
    'Patna': {
        'monsoon_months': [6, 7, 8, 9],
        'seasonal_avg_rainfall': 1100
    },
    'Guwahati': {
        'monsoon_months': [6, 7, 8, 9],
        'seasonal_avg_rainfall': 1700
    }
}


def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG)


def fetch_weather_data(conn, city_id=None, start_date=None, end_date=None):
    """
    Fetch raw weather data from PostgreSQL
    """
    query = """
        SELECT 
            wd.id,
            wd.city_id,
            c.name as city_name,
            c.latitude,
            c.longitude,
            wd.date,
            wd.rainfall_mm,
            wd.rainfall_hours,
            wd.humidity,
            wd.temp_max,
            wd.temp_min,
            wd.temp_mean
        FROM weather_daily wd
        JOIN cities c ON wd.city_id = c.id
        WHERE 1=1
    """
    
    params = []
    if city_id:
        query += " AND wd.city_id = %s"
        params.append(city_id)
    
    if start_date:
        query += " AND wd.date >= %s"
        params.append(start_date)
    
    if end_date:
        query += " AND wd.date <= %s"
        params.append(end_date)
    
    query += " ORDER BY c.name, wd.date"
    
    df = pd.read_sql_query(query, conn, params=params)
    return df


def fetch_flood_events(conn, city_id=None):
    """
    Fetch flood events for labeling
    """
    query = """
        SELECT 
            fe.city_id,
            c.name as city_name,
            fe.event_date,
            fe.severity
        FROM flood_events fe
        JOIN cities c ON fe.city_id = c.id
        WHERE 1=1
    """
    
    params = []
    if city_id:
        query += " AND fe.city_id = %s"
        params.append(city_id)
    
    df = pd.read_sql_query(query, conn, params=params)
    return df


def calculate_api_index(df, k=API_DECAY_CONSTANT):
    """
    Calculate Antecedent Precipitation Index (API) using recursive formula:
    API_t = P_t + k * API_(t-1)
    
    Args:
        df: DataFrame with rainfall data grouped by city and sorted by date
        k: decay constant (default 0.90)
    
    Returns:
        DataFrame with API index column added
    """
    df = df.copy()
    
    # Initialize API for each city
    df['api_index'] = 0.0
    
    # Calculate API per city (reset at start of each city's series)
    for city_id in df['city_id'].unique():
        city_mask = df['city_id'] == city_id
        city_data = df[city_mask].sort_values('date')
        
        # Initialize API with first day's rainfall
        if len(city_data) > 0:
            api_values = []
            current_api = 0.0
            
            for _, row in city_data.iterrows():
                rainfall = row['rainfall_mm'] if pd.notna(row['rainfall_mm']) else 0.0
                current_api = rainfall + k * current_api
                api_values.append(current_api)
            
            df.loc[city_mask, 'api_index'] = api_values
    
    return df


def calculate_rolling_features(df):
    """
    Calculate rolling rainfall features
    """
    df = df.copy()
    
    # Sort by city and date for proper rolling calculations
    df = df.sort_values(['city_id', 'date'])
    
    # Calculate rolling features per city
    for city_id in df['city_id'].unique():
        city_mask = df['city_id'] == city_id
        city_data = df[city_mask].sort_values('date')
        
        # Rainfall features
        city_data['rainfall_24h'] = city_data['rainfall_mm'].fillna(0)
        city_data['rainfall_3d'] = city_data['rainfall_mm'].rolling(window=3, min_periods=1).sum()
        city_data['rainfall_7d'] = city_data['rainfall_mm'].rolling(window=7, min_periods=1).sum()
        
        # Rainfall intensity (peak rate - using hours if available)
        if 'rainfall_hours' in city_data.columns:
            city_data['rainfall_intensity'] = np.where(
                city_data['rainfall_hours'] > 0,
                city_data['rainfall_mm'] / city_data['rainfall_hours'],
                0
            )
        else:
            city_data['rainfall_intensity'] = city_data['rainfall_mm']  # Fallback
        
        df.loc[city_mask, 'rainfall_24h'] = city_data['rainfall_24h'].values
        df.loc[city_mask, 'rainfall_3d'] = city_data['rainfall_3d'].values
        df.loc[city_mask, 'rainfall_7d'] = city_data['rainfall_7d'].values
        df.loc[city_mask, 'rainfall_intensity'] = city_data['rainfall_intensity'].values
    
    return df


def calculate_seasonal_features(df):
    """
    Calculate seasonal features
    """
    df = df.copy()
    
    # Convert date to datetime if not already
    df['date'] = pd.to_datetime(df['date'])
    
    # Extract month
    df['month'] = df['date'].dt.month
    
    # Create a mapping from city_id to city_name for configuration lookup
    # We need to join with cities to get city_name for configuration
    city_id_to_name = {}
    for city_id in df['city_id'].unique():
        # Get the city_name from the first occurrence
        city_name_row = df[df['city_id'] == city_id].iloc[0]
        # Since we don't have city_name in df, we need to look it up from the original cities
        # For now, use a simple mapping based on coordinates
        lat = city_name_row['latitude']
        lon = city_name_row['longitude']
        
        # Simple coordinate matching to city names
        if abs(lat - 19.0760) < 0.1 and abs(lon - 72.8777) < 0.1:
            city_id_to_name[city_id] = 'Mumbai'
        elif abs(lat - 13.0827) < 0.1 and abs(lon - 80.2707) < 0.1:
            city_id_to_name[city_id] = 'Chennai'
        elif abs(lat - 22.5726) < 0.1 and abs(lon - 88.3639) < 0.1:
            city_id_to_name[city_id] = 'Kolkata'
        elif abs(lat - 25.5941) < 0.1 and abs(lon - 85.1376) < 0.1:
            city_id_to_name[city_id] = 'Patna'
        elif abs(lat - 26.1445) < 0.1 and abs(lon - 91.7362) < 0.1:
            city_id_to_name[city_id] = 'Guwahati'
        else:
            city_id_to_name[city_id] = 'Mumbai'  # Default
    
    # Monsoon season flag
    df['is_monsoon_season'] = df.apply(
        lambda row: 1 if row['month'] in CITY_CONFIG.get(city_id_to_name.get(row['city_id'], 'Mumbai'), {}).get('monsoon_months', [])
        else 0,
        axis=1
    )
    
    return df


def calculate_seasonal_normal_features(df):
    """
    Calculate rainfall as percentage of seasonal normal
    """
    df = df.copy()
    
    # Create the same city_id_to_name mapping
    city_id_to_name = {}
    for city_id in df['city_id'].unique():
        city_name_row = df[df['city_id'] == city_id].iloc[0]
        lat = city_name_row['latitude']
        lon = city_name_row['longitude']
        
        if abs(lat - 19.0760) < 0.1 and abs(lon - 72.8777) < 0.1:
            city_id_to_name[city_id] = 'Mumbai'
        elif abs(lat - 13.0827) < 0.1 and abs(lon - 80.2707) < 0.1:
            city_id_to_name[city_id] = 'Chennai'
        elif abs(lat - 22.5726) < 0.1 and abs(lon - 88.3639) < 0.1:
            city_id_to_name[city_id] = 'Kolkata'
        elif abs(lat - 25.5941) < 0.1 and abs(lon - 85.1376) < 0.1:
            city_id_to_name[city_id] = 'Patna'
        elif abs(lat - 26.1445) < 0.1 and abs(lon - 91.7362) < 0.1:
            city_id_to_name[city_id] = 'Guwahati'
        else:
            city_id_to_name[city_id] = 'Mumbai'
    
    # Calculate 7-day rainfall sum
    df['rainfall_7d_sum'] = df.groupby('city_id')['rainfall_mm'].transform(
        lambda x: x.rolling(window=7, min_periods=1).sum()
    )
    
    # Calculate as percentage of seasonal normal (per day of monsoon)
    for city_id in df['city_id'].unique():
        city_mask = df['city_id'] == city_id
        city_name = city_id_to_name.get(city_id, 'Mumbai')
        city_config = CITY_CONFIG.get(city_name, {})
        seasonal_avg = city_config.get('seasonal_avg_rainfall', 1500)
        monsoon_days = len(city_config.get('monsoon_months', [6, 7, 8, 9])) * 30  # Approximate
        
        if monsoon_days > 0:
            daily_seasonal_normal = seasonal_avg / monsoon_days
            df.loc[city_mask, 'rainfall_pct_of_seasonal_normal'] = (
                df.loc[city_mask, 'rainfall_7d_sum'] / (daily_seasonal_normal * 7) * 100
            )
        else:
            df.loc[city_mask, 'rainfall_pct_of_seasonal_normal'] = 0
    
    # Clean up temporary column
    df = df.drop('rainfall_7d_sum', axis=1)
    
    return df


def add_spatial_features(df):
    """
    Add spatial features (latitude, longitude) from city data
    """
    df = df.copy()
    
    # Ensure lat/lon are included (they should already be there from weather data)
    if 'latitude' not in df.columns:
        df['latitude'] = df.groupby('city_id')['latitude'].transform('first')
    if 'longitude' not in df.columns:
        df['longitude'] = df.groupby('city_id')['longitude'].transform('first')
    
    return df


def apply_flood_labels(df, flood_events_df):
    """
    Apply flood event labels using hybrid approach:
    1. Real historical flood events
    2. Rainfall thresholds derived from real events
    """
    df = df.copy()
    
    # Initialize risk level as 0 (low risk)
    df['risk_level'] = 0
    df['risk_label'] = 'low'
    
    # Create a mapping from city_name to city_id from the data
    city_id_to_name = {}
    for city_id in df['city_id'].unique():
        city_name_row = df[df['city_id'] == city_id].iloc[0]
        lat = city_name_row['latitude']
        lon = city_name_row['longitude']
        
        if abs(lat - 19.0760) < 0.1 and abs(lon - 72.8777) < 0.1:
            city_id_to_name[city_id] = 'Mumbai'
        elif abs(lat - 13.0827) < 0.1 and abs(lon - 80.2707) < 0.1:
            city_id_to_name[city_id] = 'Chennai'
        elif abs(lat - 22.5726) < 0.1 and abs(lon - 88.3639) < 0.1:
            city_id_to_name[city_id] = 'Kolkata'
        elif abs(lat - 25.5941) < 0.1 and abs(lon - 85.1376) < 0.1:
            city_id_to_name[city_id] = 'Patna'
        elif abs(lat - 26.1445) < 0.1 and abs(lon - 91.7362) < 0.1:
            city_id_to_name[city_id] = 'Guwahati'
        else:
            city_id_to_name[city_id] = 'Mumbai'
    
    # 1. Apply flood event labels from real historical data
    for _, event in flood_events_df.iterrows():
        city = event['city_name']
        event_date = pd.to_datetime(event['event_date'])
        severity = event['severity']
        
        # Convert severity to numeric
        severity_map = {'low': 0, 'medium': 1, 'high': 2}
        risk_level = severity_map.get(severity.lower(), 1)
        
        # Find matching city_id
        matching_city_id = None
        for city_id, city_name in city_id_to_name.items():
            if city_name == city:
                matching_city_id = city_id
                break
        
        if matching_city_id is None:
            continue
            
        # Label the event date and 1-2 days after (flood impact lag)
        for lag in range(3):  # Event day + 2 days after
            target_date = event_date + pd.Timedelta(days=lag)
            
            mask = (df['city_id'] == matching_city_id) & (df['date'] == target_date)
            df.loc[mask, 'risk_level'] = risk_level
            df.loc[mask, 'risk_label'] = severity.lower()
    
    # 2. Apply rainfall threshold-based labels for better training data
    # Thresholds derived from real flood events analysis
    high_risk_thresholds = {
        'rainfall_24h': 30.0,   # 75th percentile of real high events
        'rainfall_3d': 107.0,   # 75th percentile of real high events
        'rainfall_7d': 206.0,   # 75th percentile of real high events
        'api_index': 239.0      # 75th percentile of real high events
    }
    
    medium_risk_thresholds = {
        'rainfall_24h': 23.0,   # Average of real medium events
        'rainfall_3d': 87.0,    # Average of real medium events
        'rainfall_7d': 171.0,   # Average of real medium events
        'api_index': 193.0      # Average of real medium events
    }
    
    # Apply threshold-based labeling (only for records not already labeled)
    for idx, row in df.iterrows():
        if row['risk_level'] != 0:  # Skip already labeled records
            continue
            
        # Check if meets high risk thresholds (at least 2 of 4 criteria)
        high_risk_count = 0
        if row['rainfall_24h'] >= high_risk_thresholds['rainfall_24h']:
            high_risk_count += 1
        if row['rainfall_3d'] >= high_risk_thresholds['rainfall_3d']:
            high_risk_count += 1
        if row['rainfall_7d'] >= high_risk_thresholds['rainfall_7d']:
            high_risk_count += 1
        if row['api_index'] >= high_risk_thresholds['api_index']:
            high_risk_count += 1
        
        if high_risk_count >= 2:  # At least 2 high-risk criteria met
            df.loc[idx, 'risk_level'] = 2
            df.loc[idx, 'risk_label'] = 'high'
            continue
        
        # Check if meets medium risk thresholds (at least 2 of 4 criteria)
        medium_risk_count = 0
        if row['rainfall_24h'] >= medium_risk_thresholds['rainfall_24h']:
            medium_risk_count += 1
        if row['rainfall_3d'] >= medium_risk_thresholds['rainfall_3d']:
            medium_risk_count += 1
        if row['rainfall_7d'] >= medium_risk_thresholds['rainfall_7d']:
            medium_risk_count += 1
        if row['api_index'] >= medium_risk_thresholds['api_index']:
            medium_risk_count += 1
        
        if medium_risk_count >= 2:  # At least 2 medium-risk criteria met
            df.loc[idx, 'risk_level'] = 1
            df.loc[idx, 'risk_label'] = 'medium'
    
    return df


def engineer_features(conn, city_id=None, start_date=None, end_date=None):
    """
    Main feature engineering pipeline
    """
    print("Fetching weather data...")
    weather_df = fetch_weather_data(conn, city_id, start_date, end_date)
    
    if weather_df.empty:
        print("No weather data found")
        return pd.DataFrame()
    
    print(f"Processing {len(weather_df)} weather records...")
    
    # Fetch flood events for labeling
    print("Fetching flood events...")
    flood_events_df = fetch_flood_events(conn, city_id)
    
    # Apply all feature engineering steps
    print("Calculating API index...")
    weather_df = calculate_api_index(weather_df)
    
    print("Calculating rolling features...")
    weather_df = calculate_rolling_features(weather_df)
    
    print("Calculating seasonal features...")
    weather_df = calculate_seasonal_features(weather_df)
    
    print("Calculating seasonal normal features...")
    weather_df = calculate_seasonal_normal_features(weather_df)
    
    print("Adding spatial features...")
    weather_df = add_spatial_features(weather_df)
    
    print("Applying flood labels...")
    weather_df = apply_flood_labels(weather_df, flood_events_df)
    
    # Select final feature columns (without city_name since it's not in training_data)
    feature_columns = [
        'city_id', 'date',
        'rainfall_mm', 'rainfall_hours', 'humidity', 'temp_max', 'temp_min', 'temp_mean',
        'rainfall_24h', 'rainfall_3d', 'rainfall_7d', 'rainfall_intensity',
        'api_index', 'month', 'is_monsoon_season',
        'latitude', 'longitude', 'rainfall_pct_of_seasonal_normal',
        'risk_level', 'risk_label'
    ]
    
    final_df = weather_df[feature_columns].copy()
    
    # Fill missing humidity with median or reasonable default
    if 'humidity' in final_df.columns:
        if final_df['humidity'].isnull().all():
            # If all humidity values are null, use a reasonable default
            final_df['humidity'] = 70.0  # Average humidity
        else:
            final_df['humidity'] = final_df['humidity'].fillna(final_df['humidity'].median())
    
    final_df = weather_df[feature_columns].copy()
    
    print(f"Feature engineering complete. {len(final_df)} records with {len(feature_columns)} features.")
    
    return final_df


def save_to_database(conn, df):
    """
    Save engineered features to training_data table
    """
    if df.empty:
        print("No data to save")
        return
    
    cursor = conn.cursor()
    
    print("Saving engineered features to database...")
    
    for _, row in df.iterrows():
        insert_query = """
            INSERT INTO training_data (
                city_id, date, rainfall_mm, rainfall_hours, humidity, temp_max, temp_min, temp_mean,
                rainfall_24h, rainfall_3d, rainfall_7d, rainfall_intensity,
                api_index, month, is_monsoon_season, latitude, longitude,
                rainfall_pct_of_seasonal_normal, risk_level, risk_label, data_source
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, 'feature_engineering'
            )
            ON CONFLICT (city_id, date) DO UPDATE SET
                rainfall_mm = EXCLUDED.rainfall_mm,
                rainfall_hours = EXCLUDED.rainfall_hours,
                humidity = EXCLUDED.humidity,
                temp_max = EXCLUDED.temp_max,
                temp_min = EXCLUDED.temp_min,
                temp_mean = EXCLUDED.temp_mean,
                rainfall_24h = EXCLUDED.rainfall_24h,
                rainfall_3d = EXCLUDED.rainfall_3d,
                rainfall_7d = EXCLUDED.rainfall_7d,
                rainfall_intensity = EXCLUDED.rainfall_intensity,
                api_index = EXCLUDED.api_index,
                month = EXCLUDED.month,
                is_monsoon_season = EXCLUDED.is_monsoon_season,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                rainfall_pct_of_seasonal_normal = EXCLUDED.rainfall_pct_of_seasonal_normal,
                risk_level = EXCLUDED.risk_level,
                risk_label = EXCLUDED.risk_label,
                updated_at = CURRENT_TIMESTAMP
        """
        
        values = (
            row['city_id'], row['date'], row['rainfall_mm'], row['rainfall_hours'],
            row['humidity'], row['temp_max'], row['temp_min'], row['temp_mean'],
            row['rainfall_24h'], row['rainfall_3d'], row['rainfall_7d'], row['rainfall_intensity'],
            row['api_index'], row['month'], row['is_monsoon_season'],
            row['latitude'], row['longitude'], row['rainfall_pct_of_seasonal_normal'],
            row['risk_level'], row['risk_label']
        )
        
        cursor.execute(insert_query, values)
    
    conn.commit()
    cursor.close()
    print(f"Saved {len(df)} engineered records to database")


def main():
    """Main execution function"""
    try:
        conn = get_db_connection()
        
        # Engineer features for all cities
        engineered_df = engineer_features(conn)
        
        if not engineered_df.empty:
            # Save to database
            save_to_database(conn, engineered_df)
            
            # Also save to CSV for backup/analysis
            output_path = '../data/training_data_engineered.csv'
            engineered_df.to_csv(output_path, index=False)
            print(f"Saved engineered data to {output_path}")
        
        conn.close()
        print("Feature engineering pipeline completed successfully")
        
    except Exception as e:
        print(f"Error in feature engineering: {e}")
        raise


if __name__ == "__main__":
    main()