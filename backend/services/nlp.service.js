const axios = require('axios');

const NLP_SERVICE_URL = process.env.NLP_SERVICE_URL || 'http://localhost:8000';

// Create axios instance for NLP service
const nlpClient = axios.create({
    baseURL: NLP_SERVICE_URL,
    timeout: 300000, // Increased to 300 seconds (5 mins) for complex queries
    headers: {
        'Content-Type': 'application/json'
    }
});

// Helper for error handling
const handleNlpError = (error) => {
    console.error('NLP Service Error:', error.message);

    if (error.response) {
        // NLP service returned an error
        throw new Error(error.response.data.detail || error.response.data.message || 'NLP service error');
    } else if (error.code === 'ECONNREFUSED') {
        throw new Error('NLP service is not available. Please ensure it is running.');
    } else if (error.code === 'ETIMEDOUT' || error.code === 'ECONNABORTED') {
        throw new Error('NLP service request timed out. Query may be too complex.');
    } else {
        throw new Error(`Failed to communicate with NLP service: ${error.message}`);
    }
};

// Translate natural language query to MongoDB query (Direct execution)
exports.translateQuery = async (params) => {
    try {
        const response = await nlpClient.post('/translate', params);
        return response.data;
    } catch (error) {
        handleNlpError(error);
    }
};

// Get a query plan (Planning stage)
exports.getPlan = async (params) => {
    try {
        const response = await nlpClient.post('/plan', params);
        return response.data;
    } catch (error) {
        handleNlpError(error);
    }
};

// Execute a confirmed MQL query (Execution stage)
exports.executeConfirmed = async ({ mql, database }) => {
    try {
        const response = await nlpClient.post('/execute-mql', {
            mql,
            database
        });

        return response.data;
    } catch (error) {
        handleNlpError(error);
    }
};

// Check NLP service health
exports.checkHealth = async () => {
    try {
        const response = await nlpClient.get('/health');
        return response.data;
    } catch (error) {
        throw new Error('NLP service health check failed');
    }
};

