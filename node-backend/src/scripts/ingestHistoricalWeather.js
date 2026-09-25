/**
 * Historical Weather Data Ingestion Script
 * Pulls historical weather data from Open-Meteo Archive API for all target cities
 * Usage: node src/scripts/ingestHistoricalWeather.js
 */

const axios = require('axios');
const pool = require('../config/database');
const CITIES = require('../config/cities');

// Open-Meteo Archive API configuration
const ARCHIVE_API_BASE = 'https://archive-api.open-meteo.com/v1/archive';

// Weather parameters to fetch (only available daily parameters in Open-Meteo Archive API)
const WEATHER_PARAMS = 'precipitation_sum,precipitation_hours,temperature_2m_max,temperature_2m_min,temperature_2m_mean';

/**
 * Fetch historical weather data for a single city from Open-Meteo
 */
async function fetchHistoricalWeather(city, startDate, endDate) {
  const url = `${ARCHIVE_API_BASE}?latitude=${city.latitude}&longitude=${city.longitude}&start_date=${startDate}&end_date=${endDate}&daily=${WEATHER_PARAMS}&timezone=auto`;
  
  try {
    console.log(`Fetching: ${url}`);
    const response = await axios.get(url);
    return response.data;
  } catch (error) {
    console.error(`Error fetching weather for ${city.name}:`, error.message);
    if (error.response) {
      console.error(`API Response Status: ${error.response.status}`);
      console.error(`API Response Data:`, error.response.data);
    }
    throw error;
  }
}

/**
 * Store weather data in PostgreSQL
 */
async function storeWeatherData(cityId, weatherData) {
  const client = await pool.connect();
  
  try {
    await client.query('BEGIN');
    
    const { daily, daily_units } = weatherData;
    const insertQuery = `
      INSERT INTO weather_daily (city_id, date, rainfall_mm, rainfall_hours, humidity, temp_max, temp_min, temp_mean, data_source)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
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
        null, // humidity not available in daily archive API
        daily.temperature_2m_max[i] || null,
        daily.temperature_2m_min[i] || null,
        daily.temperature_2m_mean[i] || null,
        'open-meteo'
      ];
      
      await client.query(insertQuery, values);
    }
    
    await client.query('COMMIT');
    console.log(`Stored ${daily.time.length} weather records for city ID ${cityId}`);
  } catch (error) {
    await client.query('ROLLBACK');
    console.error(`Error storing weather data for city ID ${cityId}:`, error.message);
    throw error;
  } finally {
    client.release();
  }
}

/**
 * Get or create city ID from database
 */
async function getCityId(city) {
  const result = await pool.query(
    'SELECT id FROM cities WHERE name = $1',
    [city.name]
  );
  
  if (result.rows.length > 0) {
    return result.rows[0].id;
  }
  
  // Insert city if not exists
  const insertResult = await pool.query(
    `INSERT INTO cities (name, latitude, longitude, population, geom)
     VALUES ($1, $2, $3, $4, ST_SetSRID(ST_MakePoint($3, $2), 4326))
     RETURNING id`,
    [city.name, city.latitude, city.longitude, city.population]
  );
  
  return insertResult.rows[0].id;
}

/**
 * Main ingestion function
 */
async function ingestHistoricalWeather() {
  console.log('Starting historical weather data ingestion...');
  
  // Set date range - extended to 2000 for comprehensive historical data
  const startDate = '2000-01-01'; // Extended to 2000 for more training data
  const endDate = new Date().toISOString().split('T')[0];
  
  console.log(`Fetching data from ${startDate} to ${endDate}`);
  
  for (const city of CITIES) {
    console.log(`\nProcessing ${city.name}...`);
    
    try {
      // Get city ID
      const cityId = await getCityId(city);
      console.log(`City ID: ${cityId}`);
      
      // Fetch historical weather
      const weatherData = await fetchHistoricalWeather(city, startDate, endDate);
      
      // Store in database
      await storeWeatherData(cityId, weatherData);
      
      console.log(`✅ Successfully processed ${city.name}`);
      
      // Add delay to avoid rate limiting (60 seconds between cities)
      console.log('Waiting 60 seconds to avoid rate limiting...');
      await new Promise(resolve => setTimeout(resolve, 60000));
      
    } catch (error) {
      console.error(`❌ Failed to process ${city.name}:`, error.message);
      // Continue with next city even if one fails
      
      // Add delay even on error
      console.log('Waiting 60 seconds to avoid rate limiting...');
      await new Promise(resolve => setTimeout(resolve, 60000));
    }
  }
  
  console.log('\n✅ Historical weather ingestion complete!');
}

// Run the ingestion
if (require.main === module) {
  ingestHistoricalWeather()
    .then(() => {
      console.log('Script completed successfully');
      process.exit(0);
    })
    .catch((error) => {
      console.error('Script failed:', error);
      process.exit(1);
    });
}

module.exports = { ingestHistoricalWeather, fetchHistoricalWeather, storeWeatherData };