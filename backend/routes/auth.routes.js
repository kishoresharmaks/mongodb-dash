const express = require('express');
const router = express.Router();
const {
    register,
    login,
    getMe,
    updatePreferences
} = require('../controllers/auth.controller');
const { protect } = require('../middleware/auth.middleware');

// Public routes
router.post('/register', register);
router.post('/login', login);

// Protected routes
router.get('/me', protect, getMe);
router.put('/preferences', protect, updatePreferences);

module.exports = router;
