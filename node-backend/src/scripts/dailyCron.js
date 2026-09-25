/**
 * Daily Cron Job for Live Data Ingestion and Inference
 * Runs daily to: 1) Fetch live weather, 2) Update features, 3) Trigger predictions, 4) Send alerts
 * Usage: node src/scripts/dailyCron.js
 * Schedule: Run via node-cron or system scheduler (e.g., daily at 6 AM during monsoon)
 */

const cron = require('node-cron');
const axios = require('axios');
const pool = require('../config/database');
const CITIES = require('../config/cities');
const { ingestLiveWeather } = require('./ingestLiveWeather');
const twilio = require('twilio');
const nodemailer = require('nodemailer');
const winston = require('winston');

// Configure logging
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.File({ filename: 'logs/cron-job.log' }),
    new winston.transports.Console()
  ]
});

// Alert configuration
const ALERT_CONFIG = {
  high_risk_threshold: 0.7,  // Trigger alerts for high risk probability > 70%
  phone_numbers: process.env.ALERT_PHONE_NUMBERS?.split(',') || [],
  email_recipients: process.env.ALERT_EMAILS?.split(',') || []
};

// Twilio setup
const twilioClient = process.env.TWILIO_ACCOUNT_SID 
  ? twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN)
  : null;

// Email setup
const emailTransporter = process.env.EMAIL_HOST 
  ? nodemailer.createTransport({
      host: process.env.EMAIL_HOST,
      port: process.env.EMAIL_PORT,
      secure: false,
      auth: {
        user: process.env.EMAIL_USER,
        pass: process.env.EMAIL_PASSWORD
      }
    })
  : null;

/**
 * Trigger flood risk prediction for a city
 */
async function triggerPrediction(city, date) {
  try {
    const response = await axios.post('http://localhost:8001/predict', {
      city: city.name,
      date: date,
      use_forecast: true
    });
    
    return response.data;
  } catch (error) {
    logger.error(`Prediction failed for ${city.name}:`, error.message);
    throw error;
  }
}

/**
 * Send SMS alert via Twilio
 */
async function sendSMSAlert(prediction) {
  if (!twilioClient || ALERT_CONFIG.phone_numbers.length === 0) {
    logger.warn('Twilio not configured or no phone numbers, skipping SMS');
    return;
  }
  
  const message = `
🚨 FLOOD RISK ALERT - ${prediction.city}
Date: ${prediction.date}
Risk Level: ${prediction.risk_level.toUpperCase()}
Risk Score: ${prediction.risk_score}
Action: ${prediction.recommended_action}
Timestamp: ${prediction.prediction_timestamp}
  `.trim();
  
  try {
    for (const phoneNumber of ALERT_CONFIG.phone_numbers) {
      await twilioClient.messages.create({
        body: message,
        from: process.env.TWILIO_PHONE_NUMBER,
        to: phoneNumber.trim()
      });
      logger.info(`SMS alert sent to ${phoneNumber}`);
    }
  } catch (error) {
    logger.error('Failed to send SMS alert:', error.message);
  }
}

/**
 * Send email alert
 */
async function sendEmailAlert(prediction) {
  if (!emailTransporter || ALERT_CONFIG.email_recipients.length === 0) {
    logger.warn('Email not configured or no recipients, skipping email');
    return;
  }
  
  const mailOptions = {
    from: process.env.EMAIL_FROM || 'Flood Alert System <alerts@floodsystem.com>',
    to: ALERT_CONFIG.email_recipients.join(','),
    subject: `🚨 FLOOD RISK ALERT - ${prediction.city} - ${prediction.risk_level.toUpperCase()}`,
    html: `
      <h2>🚨 Flood Risk Alert</h2>
      <p><strong>City:</strong> ${prediction.city}</p>
      <p><strong>Date:</strong> ${prediction.date}</p>
      <p><strong>Risk Level:</strong> ${prediction.risk_level.toUpperCase()}</p>
      <p><strong>Risk Score:</strong> ${prediction.risk_score}</p>
      <p><strong>Recommended Action:</strong> ${prediction.recommended_action}</p>
      <p><strong>Probabilities:</strong></p>
      <ul>
        <li>Low: ${prediction.probabilities.low}</li>
        <li>Medium: ${prediction.probabilities.medium}</li>
        <li>High: ${prediction.probabilities.high}</li>
      </ul>
      <p><strong>Contributing Factors:</strong></p>
      <ul>
        ${prediction.contributing_factors.map(f => `<li>${f.feature}: ${f.value} (importance: ${f.importance})</li>`).join('')}
      </ul>
      <p><em>Generated at: ${prediction.prediction_timestamp}</em></p>
    `
  };
  
  try {
    await emailTransporter.sendMail(mailOptions);
    logger.info(`Email alert sent to ${ALERT_CONFIG.email_recipients.join(', ')}`);
  } catch (error) {
    logger.error('Failed to send email alert:', error.message);
  }
}

/**
 * Log prediction to database for monitoring
 */
async function logPrediction(conn, prediction) {
  try {
    const insertQuery = `
      INSERT INTO predictions_log (
        city_id, prediction_date, target_date, predicted_risk_level, 
        predicted_risk_label, risk_score, features_used, model_version, 
        was_alert_triggered
      )
      VALUES (
        (SELECT id FROM cities WHERE name = $1),
        CURRENT_TIMESTAMP,
        $2,
        $3,
        $4,
        $5,
        $6,
        $7,
        $8
      )
    `;
    
    const cityId = await pool.query('SELECT id FROM cities WHERE name = $1', [prediction.city]);
    
    if (cityId.rows.length > 0) {
      await pool.query(insertQuery, [
        prediction.city,
        prediction.date,
        prediction.risk_level === 'high' ? 2 : prediction.risk_level === 'medium' ? 1 : 0,
        prediction.risk_level,
        prediction.risk_score,
        JSON.stringify(prediction.contributing_factors),
        prediction.model_version,
        prediction.should_alert
      ]);
    }
  } catch (error) {
    logger.error('Failed to log prediction:', error.message);
  }
}

/**
 * Main daily cron job function
 */
async function dailyCronJob() {
  logger.info('Starting daily cron job...');
  
  const conn = await pool.connect();
  const today = new Date().toISOString().split('T')[0];
  
  try {
    // Step 1: Ingest live weather data
    logger.info('Step 1: Ingesting live weather data...');
    await ingestLiveWeather();
    
    // Step 2: For each city, trigger prediction
    logger.info('Step 2: Triggering predictions for all cities...');
    
    for (const city of CITIES) {
      try {
        logger.info(`Processing ${city.name}...`);
        
        // Trigger prediction
        const prediction = await triggerPrediction(city, today);
        logger.info(`Prediction for ${city.name}: ${prediction.risk_level} (score: ${prediction.risk_score})`);
        
        // Log prediction to database
        await logPrediction(conn, prediction);
        
        // Step 3: Send alerts if high risk
        if (prediction.should_alert && prediction.risk_level === 'high') {
          logger.info(`High risk detected for ${city.name}, sending alerts...`);
          
          await sendSMSAlert(prediction);
          await sendEmailAlert(prediction);
          
          logger.info(`Alerts sent for ${city.name}`);
        } else {
          logger.info(`No alerts needed for ${city.name}`);
        }
        
      } catch (error) {
        logger.error(`Error processing ${city.name}:`, error.message);
        // Continue with next city even if one fails
      }
    }
    
    logger.info('✅ Daily cron job completed successfully');
    
  } catch (error) {
    logger.error('Daily cron job failed:', error);
    throw error;
  } finally {
    conn.release();
  }
}

/**
 * Schedule the cron job to run daily at 6 AM
 */
function scheduleCronJob() {
  // Run daily at 6:00 AM
  cron.schedule('0 6 * * *', async () => {
    logger.info('Scheduled cron job triggered at 6:00 AM');
    await dailyCronJob();
  });
  
  logger.info('Cron job scheduled to run daily at 6:00 AM');
}

// Run immediately if called directly, or schedule if imported
if (require.main === module) {
  const args = process.argv.slice(2);
  
  if (args.includes('--schedule')) {
    // Schedule the cron job
    scheduleCronJob();
    logger.info('Cron job scheduler started. Press Ctrl+C to stop.');
    
    // Keep the process running
    process.on('SIGINT', () => {
      logger.info('Cron job scheduler stopped');
      process.exit(0);
    });
  } else {
    // Run once immediately
    dailyCronJob()
      .then(() => {
        logger.info('Cron job completed');
        process.exit(0);
      })
      .catch((error) => {
        logger.error('Cron job failed:', error);
        process.exit(1);
      });
  }
}

module.exports = { dailyCronJob, scheduleCronJob };