/**
 * Flood Events CSV Loading Script
 * Loads manually compiled flood event data into PostgreSQL
 * Usage: node src/scripts/loadFloodEvents.js
 */

const fs = require('fs');
const path = require('path');
const csv = require('csv-parser');
const pool = require('../config/database');

const FLOOD_EVENTS_CSV = path.join(__dirname, '../../../data/flood_events_template.csv');

/**
 * Load flood events from CSV file
 */
async function loadFloodEvents() {
  console.log('Loading flood events from CSV...');
  
  const client = await pool.connect();
  
  try {
    await client.query('BEGIN');
    
    const results = [];
    
    await new Promise((resolve, reject) => {
      fs.createReadStream(FLOOD_EVENTS_CSV)
        .pipe(csv())
        .on('data', (row) => {
          results.push(row);
        })
        .on('end', resolve)
        .on('error', reject);
    });
    
    console.log(`Found ${results.length} flood events in CSV`);
    
    // Insert each flood event
    for (const row of results) {
      try {
        // Get city ID
        const cityResult = await client.query(
          'SELECT id FROM cities WHERE name = $1',
          [row.city]
        );
        
        if (cityResult.rows.length === 0) {
          console.warn(`City not found: ${row.city}, skipping event`);
          continue;
        }
        
        const cityId = cityResult.rows[0].id;
        
        // Insert flood event
        const insertQuery = `
          INSERT INTO flood_events (city_id, event_date, severity, description, source, affected_population, economic_loss_usd, casualties)
          VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
          ON CONFLICT (city_id, event_date) DO UPDATE SET
            severity = EXCLUDED.severity,
            description = EXCLUDED.description,
            source = EXCLUDED.source,
            affected_population = EXCLUDED.affected_population,
            economic_loss_usd = EXCLUDED.economic_loss_usd,
            casualties = EXCLUDED.casualties,
            updated_at = CURRENT_TIMESTAMP
        `;
        
        const values = [
          cityId,
          row.event_date,
          row.severity,
          row.description,
          row.source,
          row.affected_population ? parseInt(row.affected_population) : null,
          row.economic_loss_usd ? parseFloat(row.economic_loss_usd) : null,
          row.casualties ? parseInt(row.casualties) : null
        ];
        
        await client.query(insertQuery, values);
        console.log(`✅ Loaded flood event for ${row.city} on ${row.event_date}`);
        
      } catch (error) {
        console.error(`Error loading event for ${row.city} on ${row.event_date}:`, error.message);
      }
    }
    
    await client.query('COMMIT');
    console.log('\n✅ Flood events loaded successfully!');
    
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error loading flood events:', error.message);
    throw error;
  } finally {
    client.release();
  }
}

// Run the loading
if (require.main === module) {
  loadFloodEvents()
    .then(() => {
      console.log('Script completed successfully');
      process.exit(0);
    })
    .catch((error) => {
      console.error('Script failed:', error);
      process.exit(1);
    });
}

module.exports = { loadFloodEvents };