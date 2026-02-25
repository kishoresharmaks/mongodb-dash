const express = require('express');
const router = express.Router();
const {
    getPolicies,
    createPolicy,
    updatePolicy,
    getUsers,
    updateUserRole
} = require('../controllers/admin.controller');
const { getConfig, updateConfig, getMetadataCollections, resetConfig } = require('../controllers/config.controller');
const { protect, admin } = require('../middleware/auth.middleware');

// Protect all admin routes
router.use(protect);
// router.use(admin); // Will enable after seeding first admin

router.get('/policies', getPolicies);
router.post('/policies', createPolicy);
router.put('/policies/:id', updatePolicy);

router.get('/users', getUsers);
router.put('/users/:id/role', updateUserRole);

// System Config
router.get('/config/:key', getConfig);
router.post('/config', updateConfig);
router.post('/config/reset', resetConfig);

// Metadata
router.get('/metadata/collections', getMetadataCollections);

module.exports = router;
