#!/usr/bin/env python3
"""
Flood Risk Prediction System Setup Script (Python-based)
This script works even if PostgreSQL is not in PATH
"""

import subprocess
import sys
import os
import json
from pathlib import Path

def check_command(cmd):
    """Check if a command is available"""
    try:
        subprocess.run([cmd, '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"🔄 {description}...")
    try:
        # Handle commands with spaces in paths
        if isinstance(cmd, str):
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        else:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False

def setup_postgresql_python():
    """Setup PostgreSQL using Python instead of psql command"""
    print("🔧 Setting up PostgreSQL using Python...")
    
    # Install psycopg if not available
    try:
        import psycopg
        print("✅ psycopg already installed")
    except ImportError:
        print("📦 Installing psycopg...")
        subprocess.run([sys.executable, "-m", "pip", "install", "psycopg[binary]"], check=True)
        import psycopg
    
    # Get database credentials
    print("\n📝 PostgreSQL Configuration:")
    db_name = input("Enter PostgreSQL database name (default: flood_risk_db): ").strip() or "flood_risk_db"
    db_user = input("Enter PostgreSQL user (default: postgres): ").strip() or "postgres"
    db_password = input("Enter PostgreSQL password: ").strip()
    db_host = input("Enter PostgreSQL host (default: localhost): ").strip() or "localhost"
    db_port = input("Enter PostgreSQL port (default: 5432): ").strip() or "5432"
    
    # Create .env file
    env_content = f"""DB_HOST={db_host}
DB_PORT={db_port}
DB_NAME={db_name}
DB_USER={db_user}
DB_PASSWORD={db_password}
"""
    
    env_path = Path("node-backend/.env")
    env_path.parent.mkdir(exist_ok=True)
    with open(env_path, 'w') as f:
        f.write(env_content)
    print(f"✅ Created {env_path}")
    
    # Test database connection and create database
    try:
        # Connect to default postgres database first
        try:
            conn = psycopg.connect(
                host=db_host,
                port=db_port,
                dbname="postgres",
                user=db_user,
                password=db_password
            )
        except NameError:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                database="postgres",
                user=db_user,
                password=db_password
            )
        
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
        if not cursor.fetchone():
            print(f"🗄️  Creating database '{db_name}'...")
            cursor.execute(f"CREATE DATABASE {db_name}")
            print(f"✅ Database '{db_name}' created")
        else:
            print(f"✅ Database '{db_name}' already exists")
        
        cursor.close()
        conn.close()
        
        # Connect to the new database and run schema
        print("📋 Running database schema...")
        try:
            conn = psycopg.connect(
                host=db_host,
                port=db_port,
                dbname=db_name,
                user=db_user,
                password=db_password
            )
        except NameError:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password
            )
        
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Read and execute schema
        schema_path = Path("node-backend/database/schema.sql")
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            # Split and execute statements
            statements = schema_sql.split(';')
            for statement in statements:
                if statement.strip():
                    try:
                        cursor.execute(statement)
                    except Exception as e:
                        print(f"⚠️  SQL Warning: {e}")
            
            print("✅ Database schema created successfully")
        else:
            print(f"❌ Schema file not found: {schema_path}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ PostgreSQL setup failed: {e}")
        print("\n💡 Manual setup instructions:")
        print("1. Open pgAdmin or use psql directly")
        print("2. Create database: CREATE DATABASE flood_risk_db;")
        print("3. Run schema: psql -d flood_risk_db -f node-backend/database/schema.sql")
        return False
    
    return True

def main():
    print("🌊 Flood Risk Prediction System Setup (Python-based)")
    print("=" * 50)
    print()
    
    # Check prerequisites
    print("🔍 Checking prerequisites...")
    
    if not check_command('node'):
        print("❌ Node.js is not installed. Please install Node.js 18+")
        sys.exit(1)
    print("✅ Node.js found")
    
    if not check_command('python'):
        print("❌ Python is not installed. Please install Python 3.9+")
        sys.exit(1)
    print("✅ Python found")
    
    print("⚠️  PostgreSQL check skipped (will use Python for database operations)")
    print()
    
    # Install dependencies
    print("📦 Installing dependencies...")
    
    # Node.js dependencies
    os.chdir("node-backend")
    if not run_command("npm install", "Installing Node.js dependencies"):
        sys.exit(1)
    
    # Python dependencies
    os.chdir("../python-ml")
    pip_cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
    try:
        print("🔄 Installing Python dependencies...")
        subprocess.run(pip_cmd, check=True, capture_output=True, text=True)
        print("✅ Installing Python dependencies completed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Installing Python dependencies failed: {e.stderr}")
        sys.exit(1)
    
    os.chdir("..")
    
    # Setup PostgreSQL using Python
    if not setup_postgresql_python():
        print("⚠️  PostgreSQL setup encountered issues, but continuing...")
    
    # Load flood events
    print("\n📥 Loading flood events...")
    os.chdir("node-backend")
    if not run_command("node src/scripts/loadFloodEvents.js", "Loading flood events"):
        print("⚠️  Flood events loading failed (may need manual intervention)")
    
    os.chdir("..")
    
    print("\n" + "=" * 50)
    print("⚙️  System setup complete!")
    print()
    print("Next steps:")
    print("1. Edit node-backend/.env to add your Twilio and email credentials")
    print("2. Run: cd node-backend && node src/scripts/ingestHistoricalWeather.js")
    print("3. Run: cd python-ml && python feature_engineering.py")
    print("4. Run: python train_model.py")
    print("5. Start the ML service: python fastapi_service.py")
    print("6. Start the cron job: cd node-backend && node src/scripts/dailyCron.js --schedule")
    print()
    print("🎉 Setup complete! Your flood risk prediction system is ready to configure.")

if __name__ == "__main__":
    main()