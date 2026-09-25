/**
 * Live Weather Data Ingestion Script
 * Pulls current weather data from Open-Meteo Forecast API for all target cities
 * Usage: node src/scripts/ingestLiveWeather.js
 */

const axios = require('axios');
const pool = require('../config/database');
const CITIES = require('../config/cities');

// Open-Meteo Forecast API configuration
const FORECAST_API_BASE = 'https://api.open-meteo.com/v1/forecast';

// Weather parameters to fetch (only available daily parameters in Open-Meteo Forecast API)
const WEATHER_PARAMS = 'precipitation_sum,precipitation_hours,temperature_2m_max,temperature_2m_min,temperature_2m_mean';

/**
 * Fetch live/forecast weather data for a single city from Open-Meteo
 */
async function fetchLiveWeather(city) {
  const url = `${FORECAST_API_BASE}?latitude=${city.latitude}&longitude=${city.longitude}&daily=${WEATHER_PARAMS}&timezone=auto&forecast_days=7`;
  
  try {
    const response = await axios.get(url);
    return response.data;
  } catch (error) {
    console.error(`Error fetching live weather for ${city.name}:`, error.message);
    throw error;
  }
}

/**
 * Store live weather data in PostgreSQL
 */
async function storeLiveWeatherData(cityId, weatherData) {
  const client = await pool.connect();
  
  try {
    await client.query('BEGIN');
    
    const { daily, daily_units } = weatherData;
    const insertQuery = `
      INSERT INTO weather_daily (city_id, date, rainfall_mm, rainfall_hours, humidity, temp_max, temp_min, temp_mean, data_source)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'open-meteo-live')
      ON CONFLICT (city_id, date) DO UPDATE SET
        rainfall_mm = EXCLUDED.rainfall_mm,
        rainfall_hours = EXCLUDED.rainfall_hours,
        humidity = EXCLUDED.humidity,
        temp_max = EXCLUDED.temp_max,
        temp_min = EXCLUDED.temp_min,
        temp_mean = EXCLUDED.temp_mean,
        updated_at = CURRENT_TIMESTAMP
    `;
    
    for (let i = 0; i < daily.time.length; i++) {
      const values = [
        cityId,
        daily.time[i],
        daily.precipitation_sum[i] || 0,
        daily.precipitation_hours[i] || 0,
        null, // humidity not available in daily forecast API
        daily.temperature_2m_max[i] || null,
        daily.temperature_2m_min[i] || null,
        daily.temperature_2m_mean[i] || null
      ];
      
      await client.query(insertQuery, values);
    }
    
    await client.query('COMMIT');
    console.log(`Stored ${daily.time.length} live weather records for city ID ${cityId}`);
  } catch (error) {
    await client.query('ROLLBACK');
    console.error(`Error storing live weather data for city ID ${cityId}:`, error.message);
    throw error;
  } finally {
    client.release();
  }
}

/**
 * Get city ID from database
 */
async function getCityId(city) {
  const result = await pool.query(
    'SELECT id FROM cities WHERE name = $1',
    [city.name]
  );
  
  if (result.rows.length > 0) {
    return result.rows[0].id;
  }
  
  throw new Error(`City ${city.name} not found in database`);
}

/**
 * Main live weather ingestion function
 */
async function ingestLiveWeather() {
  console.log('Starting live weather data ingestion...');
  
  for (const city of CITIES) {
    console.log(`\nProcessing ${city.name}...`);
    
    try {
      // Get city ID
      const cityId = await getCityId(city);
      console.log(`City ID: ${cityId}`);
      
      // Fetch live/forecast weather
      const weatherData = await fetchLiveWeather(city);
      
      // Store in database
      await storeLiveWeatherData(cityId, weatherData);
      
      console.log(`✅ Successfully processed ${city.name}`);
    } catch (error) {
      console.error(`❌ Failed to process ${city.name}:`, error.message);
      // Continue with next city even if one fails
    }
  }
  
  console.log('\n✅ Live weather ingestion complete!');
}

// Run the ingestion
if (require.main === module) {
  ingestLiveWeather()
    .then(() => {
      console.log('Script completed successfully');
      process.exit(0);
    })
    .catch((error) => {
      console.error('Script failed:', error);
      process.exit(1);
    });
}

module.exports = { ingestLiveWeather, fetchLiveWeather, storeLiveWeatherData };