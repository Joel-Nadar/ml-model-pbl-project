// Target Indian cities with exact coordinates from requirements
const CITIES = [
  {
    name: 'Mumbai',
    latitude: 19.0760,
    longitude: 72.8777,
    population: 12440000,
    monsoon_months: [6, 7, 8, 9], // June-September
    seasonal_avg_rainfall: 2400 // mm during monsoon season (approximate)
  },
  {
    name: 'Chennai',
    latitude: 13.0827,
    longitude: 80.2707,
    population: 7046000,
    monsoon_months: [10, 11, 12], // Northeast monsoon Oct-Dec
    seasonal_avg_rainfall: 1200 // mm during monsoon season (approximate)
  },
  {
    name: 'Kolkata',
    latitude: 22.5726,
    longitude: 88.3639,
    population: 4497000,
    monsoon_months: [6, 7, 8, 9], // June-September
    seasonal_avg_rainfall: 1600 // mm during monsoon season (approximate)
  },
  {
    name: 'Patna',
    latitude: 25.5941,
    longitude: 85.1376,
    population: 2094000,
    monsoon_months: [6, 7, 8, 9], // June-September
    seasonal_avg_rainfall: 1100 // mm during monsoon season (approximate)
  },
  {
    name: 'Guwahati',
    latitude: 26.1445,
    longitude: 91.7362,
    population: 967000,
    monsoon_months: [6, 7, 8, 9], // June-September
    seasonal_avg_rainfall: 1700 // mm during monsoon season (approximate)
  }
];

module.exports = CITIES;