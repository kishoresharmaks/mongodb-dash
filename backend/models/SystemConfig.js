const mongoose = require('mongoose');

const SystemConfigSchema = new mongoose.Schema({
    key: {
        type: String,
        required: true,
        unique: true,
        default: 'main_system_prompt'
    },
    value: {
        type: String,
        required: true
    },
    description: {
        type: String
    },
    lastUpdatedBy: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
    },
    updatedAt: {
        type: Date,
        default: Date.now
    }
});

module.exports = mongoose.model('SystemConfig', SystemConfigSchema);
