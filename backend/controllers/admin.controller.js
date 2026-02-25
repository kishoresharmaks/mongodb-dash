const RolePolicy = require('../models/RolePolicy');
const User = require('../models/User');

// @desc    Get all role policies
// @route   GET /api/admin/policies
// @access  Private/Admin
exports.getPolicies = async (req, res) => {
    try {
        const policies = await RolePolicy.find();
        res.status(200).json({ success: true, data: policies });
    } catch (error) {
        res.status(500).json({ success: false, message: error.message });
    }
};

// @desc    Create a role policy
// @route   POST /api/admin/policies
// @access  Private/Admin
exports.createPolicy = async (req, res) => {
    try {
        const policy = await RolePolicy.create(req.body);
        res.status(201).json({ success: true, data: policy });
    } catch (error) {
        res.status(400).json({ success: false, message: error.message });
    }
};

// @desc    Update a role policy
// @route   PUT /api/admin/policies/:id
// @access  Private/Admin
exports.updatePolicy = async (req, res) => {
    try {
        const policy = await RolePolicy.findByIdAndUpdate(req.params.id, req.body, {
            new: true,
            runValidators: true
        });
        if (!policy) return res.status(404).json({ success: false, message: 'Policy not found' });
        res.status(200).json({ success: true, data: policy });
    } catch (error) {
        res.status(400).json({ success: false, message: error.message });
    }
};

// @desc    Get all users
// @route   GET /api/admin/users
// @access  Private/Admin
exports.getUsers = async (req, res) => {
    try {
        const users = await User.find().select('-password');
        res.status(200).json({ success: true, data: users });
    } catch (error) {
        res.status(500).json({ success: false, message: error.message });
    }
};

// @desc    Update user role
// @route   PUT /api/admin/users/:id/role
// @access  Private/Admin
exports.updateUserRole = async (req, res) => {
    try {
        const { role, rolePolicy } = req.body;
        const user = await User.findByIdAndUpdate(req.params.id,
            { role, rolePolicy },
            { new: true, runValidators: true }
        );
        if (!user) return res.status(404).json({ success: false, message: 'User not found' });
        res.status(200).json({ success: true, data: user });
    } catch (error) {
        res.status(400).json({ success: false, message: error.message });
    }
};
