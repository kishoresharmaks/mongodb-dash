const mongoose = require('mongoose');

const rolePolicySchema = new mongoose.Schema({
    name: {
        type: String,
        required: [true, 'Role name is required'],
        unique: true,
        trim: true
    },
    description: {
        type: String,
        required: [true, 'Role description is required']
    },
    permissions: {
        collections: [{
            database: {
                type: String,
                default: '*',
                comment: 'Database name or * for all databases'
            },
            name: { type: String, required: true },
            operations: {
                type: [String],
                enum: ['find', 'aggregate', 'insert', 'update', 'delete'],
                default: ['find']
            },
            fields: {
                type: [String],
                default: ['*'], // '*' means all fields
                comment: 'List of allowed fields. Use * for all.'
            },
            restrictedFields: {
                type: [String],
                default: [],
                comment: 'Explicitly blocked fields (e.g., salary, pii)'
            }
        }],
        maxLimit: {
            type: Number,
            default: 100
        }
    },
    isDefault: {
        type: Boolean,
        default: false
    }
}, {
    timestamps: true
});

module.exports = mongoose.model('RolePolicy', rolePolicySchema);
