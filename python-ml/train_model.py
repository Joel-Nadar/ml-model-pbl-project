"""
XGBoost Model Training Script for Flood Risk Prediction
Implements time-based split and spatial features for generalization across cities
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_recall_curve
from sklearn.preprocessing import StandardScaler
import joblib
import json
from datetime import datetime
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import matplotlib.pyplot as plt
import seaborn as sns

load_dotenv('../node-backend/.env')

# Database connection
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', 5432),
    'database': os.getenv('DB_NAME', 'flood_risk_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD')
}

# Model configuration
MODEL_CONFIG = {
    'n_estimators': 500,
    'learning_rate': 0.05,
    'max_depth': 6,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'min_child_weight': 3,
    'reg_lambda': 1.5,
    'random_state': 42,
    'objective': 'multi:softprob',
    'num_class': 3,  # low, medium, high
    'eval_metric': 'mlogloss',
    'tree_method': 'hist'
}

# Feature columns for training
FEATURE_COLUMNS = [
    'rainfall_24h', 'rainfall_3d', 'rainfall_7d', 'rainfall_intensity',
    'api_index', 'month', 'is_monsoon_season',
    'latitude', 'longitude', 'rainfall_pct_of_seasonal_normal',
    'humidity', 'temp_max', 'temp_min', 'temp_mean'
]

# Time split configuration (train on older data, validate on recent)
TRAIN_END_DATE = '2023-12-31'  # Train up to end of 2023
VALID_END_DATE = '2024-06-30'  # Validate on first half of 2024
# Test on second half of 2024 onwards


def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG)


def fetch_training_data(conn):
    """
    Fetch engineered training data from PostgreSQL
    """
    query = """
        SELECT 
            td.city_id, c.name as city_name, td.date,
            td.rainfall_24h, td.rainfall_3d, td.rainfall_7d, td.rainfall_intensity,
            td.api_index, td.month, td.is_monsoon_season,
            td.latitude, td.longitude, td.rainfall_pct_of_seasonal_normal,
            td.humidity, td.temp_max, td.temp_min, td.temp_mean,
            td.risk_level, td.risk_label
        FROM training_data td
        JOIN cities c ON td.city_id = c.id
        WHERE td.risk_level IS NOT NULL
        ORDER BY c.name, td.date
    """
    
    df = pd.read_sql_query(query, conn)
    return df


def time_based_split(df):
    """
    Split data by time to prevent data leakage
    Train: Up to TRAIN_END_DATE
    Validate: TRAIN_END_DATE to VALID_END_DATE  
    Test: After VALID_END_DATE
    """
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    
    train = df[df['date'] <= pd.Timestamp(TRAIN_END_DATE)]
    valid = df[(df['date'] > pd.Timestamp(TRAIN_END_DATE)) & (df['date'] <= pd.Timestamp(VALID_END_DATE))]
    test = df[df['date'] > pd.Timestamp(VALID_END_DATE)]
    
    print(f"Train set: {len(train)} samples ({train['date'].min()} to {train['date'].max()})")
    print(f"Valid set: {len(valid)} samples ({valid['date'].min()} to {valid['date'].max()})")
    print(f"Test set: {len(test)} samples ({test['date'].min()} to {test['date'].max()})")
    
    return train, valid, test


def prepare_features(df, feature_columns):
    """
    Prepare feature matrix and handle missing values
    """
    # Select feature columns
    X = df[feature_columns].copy()
    
    # Convert all columns to numeric
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce')
    
    # Handle missing values - fill with median for numeric columns
    for col in X.columns:
        if X[col].isnull().any():
            median_val = X[col].median()
            X[col] = X[col].fillna(median_val)
    
    return X


def prepare_labels(df):
    """
    Prepare labels for training
    """
    y = df['risk_level'].values
    return y


def calculate_class_weights(y):
    """
    Calculate class weights to handle imbalance
    Focus on high recall for high-risk class
    """
    classes, counts = np.unique(y, return_counts=True)
    total_samples = len(y)
    
    # Calculate weights inversely proportional to class frequency
    weights = {}
    for cls, count in zip(classes, counts):
        # Give extra weight to high-risk class (class 2) for better recall
        if cls == 2:
            weights[cls] = total_samples / (len(classes) * count) * 5.0  # 5x weight for high risk (increased from 3x)
        elif cls == 1:
            weights[cls] = total_samples / (len(classes) * count) * 2.0  # 2x weight for medium risk
        else:
            weights[cls] = total_samples / (len(classes) * count)  # Normal weight for low risk
    
    # Convert to sample weights array
    sample_weights = np.array([weights[cls] for cls in y])
    
    return weights, sample_weights


def train_xgboost_model(X_train, y_train, X_valid, y_valid):
    """
    Train XGBoost model with spatial features
    """
    print("Training XGBoost model...")
    
    # Calculate class weights
    class_weights, sample_weights = calculate_class_weights(y_train)
    
    # Initialize XGBoost classifier
    model = xgb.XGBClassifier(**MODEL_CONFIG)
    
    # Train with sample weights
    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_valid, y_valid)],
        verbose=False
    )
    
    print("Model training completed")
    
    # Store the high-risk threshold in the model for use during inference
    model.high_risk_threshold = 0.3  # 30% probability threshold + rainfall rules
    
    return model


def evaluate_model(model, X, y, set_name="Validation"):
    """
    Evaluate model performance with focus on high-risk recall
    """
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)
    
    # Adjust predictions to favor high-risk for safety using threshold-based rules
    # Combine model predictions with rainfall threshold rules for balanced performance
    high_risk_thresholds = {
        'rainfall_24h': 30.0,
        'rainfall_3d': 107.0,
        'rainfall_7d': 206.0,
        'api_index': 239.0
    }
    
    X_array = X.values if isinstance(X, pd.DataFrame) else X
    
    for i in range(len(y_pred)):
        # Check if features meet high-risk rainfall thresholds
        high_risk_count = 0
        if 'rainfall_24h' in FEATURE_COLUMNS:
            idx = FEATURE_COLUMNS.index('rainfall_24h')
            if X_array[i, idx] >= high_risk_thresholds['rainfall_24h']:
                high_risk_count += 1
        if 'rainfall_3d' in FEATURE_COLUMNS:
            idx = FEATURE_COLUMNS.index('rainfall_3d')
            if X_array[i, idx] >= high_risk_thresholds['rainfall_3d']:
                high_risk_count += 1
        if 'rainfall_7d' in FEATURE_COLUMNS:
            idx = FEATURE_COLUMNS.index('rainfall_7d')
            if X_array[i, idx] >= high_risk_thresholds['rainfall_7d']:
                high_risk_count += 1
        if 'api_index' in FEATURE_COLUMNS:
            idx = FEATURE_COLUMNS.index('api_index')
            if X_array[i, idx] >= high_risk_thresholds['api_index']:
                high_risk_count += 1
        
        # Override model prediction if rainfall thresholds are met
        if high_risk_count >= 2:  # 2 criteria needed for balanced performance
            y_pred[i] = 2
        elif y_proba[i, 2] > 0.3:  # Probability threshold
            y_pred[i] = 2
    
    # Classification report
    print(f"\n{set_name} Classification Report:")
    print(classification_report(y, y_pred, target_names=['low', 'medium', 'high']))
    
    # Confusion matrix
    cm = confusion_matrix(y, y_pred)
    print(f"\n{set_name} Confusion Matrix:")
    print(cm)
    
    # Calculate metrics
    report = classification_report(y, y_pred, target_names=['low', 'medium', 'high'], output_dict=True)
    
    metrics = {
        'set': set_name,
        'macro_f1': f1_score(y, y_pred, average='macro'),
        'weighted_f1': f1_score(y, y_pred, average='weighted'),
        'high_recall': report['high']['recall'],
        'high_precision': report['high']['precision'],
        'high_f1': report['high']['f1-score'],
        'confusion_matrix': cm.tolist(),
        'per_class_metrics': report
    }
    
    # Calculate precision-recall for high risk
    high_risk_proba = y_proba[:, 2]  # Probability of high risk
    if len(np.unique(y)) > 1:  # Only calculate if we have both classes
        precision, recall, _ = precision_recall_curve((y == 2).astype(int), high_risk_proba)
        metrics['high_risk_pr_curve'] = {
            'precision': precision.tolist(),
            'recall': recall.tolist()
        }
    else:
        metrics['high_risk_pr_curve'] = {
            'precision': [],
            'recall': []
        }
    
    return metrics


def analyze_feature_importance(model, feature_columns):
    """
    Analyze and return feature importance
    """
    importance = model.feature_importances_
    feature_importance = dict(zip(feature_columns, importance))
    
    # Sort by importance
    sorted_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
    
    return sorted_importance


def plot_feature_importance(feature_importance, output_path):
    """
    Plot feature importance
    """
    plt.figure(figsize=(10, 6))
    features = list(feature_importance.keys())
    importances = list(feature_importance.values())
    
    plt.barh(features, importances)
    plt.xlabel('Feature Importance')
    plt.title('XGBoost Feature Importance for Flood Risk Prediction')
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    
    print(f"Feature importance plot saved to {output_path}")


def save_model_and_metadata(model, metrics, feature_importance, output_dir):
    """
    Save trained model and metadata
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Save model
    model_path = os.path.join(output_dir, 'flood_risk_model.joblib')
    joblib.dump(model, model_path)
    print(f"Model saved to {model_path}")
    
    # Convert numpy types to Python types for JSON serialization
    def convert_to_json_serializable(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: convert_to_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_json_serializable(item) for item in obj]
        return obj
    
    # Save metadata
    metadata = {
        'model_type': 'XGBoost',
        'model_version': datetime.now().strftime('%Y.%m.%d-%H%M'),
        'trained_at': datetime.now().isoformat(),
        'target_cities': ['Mumbai', 'Chennai', 'Kolkata', 'Patna', 'Guwahati'],
        'feature_columns': FEATURE_COLUMNS,
        'model_config': MODEL_CONFIG,
        'training_split': {
            'train_end': TRAIN_END_DATE,
            'valid_end': VALID_END_DATE
        },
        'metrics': convert_to_json_serializable(metrics),
        'feature_importance': convert_to_json_serializable(feature_importance)
    }
    
    metadata_path = os.path.join(output_dir, 'model_metadata.json')
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to {metadata_path}")
    
    # Plot and save feature importance
    plot_path = os.path.join(output_dir, 'feature_importance.png')
    plot_feature_importance(feature_importance, plot_path)


def main():
    """Main training pipeline"""
    print("Starting XGBoost model training for flood risk prediction...")
    
    try:
        # Connect to database
        conn = get_db_connection()
        print("Connected to database")
        
        # Fetch training data
        print("Fetching training data...")
        df = fetch_training_data(conn)
        print(f"Loaded {len(df)} training samples")
        
        if df.empty:
            print("No training data found. Please run feature engineering first.")
            return
        
        # Check class distribution
        print("\nClass distribution:")
        print(df['risk_label'].value_counts())
        
        # Time-based split
        print("\nPerforming time-based split...")
        train, valid, test = time_based_split(df)
        
        # Prepare features and labels
        print("Preparing features and labels...")
        X_train = prepare_features(train, FEATURE_COLUMNS)
        y_train = prepare_labels(train)
        X_valid = prepare_features(valid, FEATURE_COLUMNS)
        y_valid = prepare_labels(valid)
        X_test = prepare_features(test, FEATURE_COLUMNS)
        y_test = prepare_labels(test)
        
        # Train model
        model = train_xgboost_model(X_train, y_train, X_valid, y_valid)
        
        # Evaluate on validation set
        valid_metrics = evaluate_model(model, X_valid, y_valid, "Validation")
        
        # Evaluate on test set
        test_metrics = evaluate_model(model, X_test, y_test, "Test")
        
        # Analyze feature importance
        feature_importance = analyze_feature_importance(model, FEATURE_COLUMNS)
        print("\nTop 10 Most Important Features:")
        for i, (feat, imp) in enumerate(list(feature_importance.items())[:10]):
            print(f"{i+1}. {feat}: {imp:.4f}")
        
        # Save model and metadata
        output_dir = '../artifacts'
        combined_metrics = {
            'validation': valid_metrics,
            'test': test_metrics
        }
        save_model_and_metadata(model, combined_metrics, feature_importance, output_dir)
        
        conn.close()
        print("\nModel training completed successfully!")
        
    except Exception as e:
        print(f"Error in model training: {e}")
        raise


if __name__ == "__main__":
    main()