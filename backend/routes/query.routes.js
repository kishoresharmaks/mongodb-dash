const express = require('express');
const router = express.Router();
const {
    executeQuery,
    getQueryPlan,
    executeConfirmedQuery,
    getHistory,
    getConversation,
    deleteQuery
} = require('../controllers/query.controller');
const { protect } = require('../middleware/auth.middleware');

// All routes are protected
router.use(protect);

router.post('/execute', executeQuery);
router.post('/plan', getQueryPlan);
router.post('/execute-confirmed', executeConfirmedQuery);
router.get('/history', getHistory);
router.get('/conversation/:conversationId', getConversation);
router.delete('/history/:id', deleteQuery);

module.exports = router;
