const mongoose = require('mongoose');

const queryHistorySchema = new mongoose.Schema({
    userId: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User',
        required: true,
        index: true
    },
    conversationId: {
        type: String,
        required: true,
        index: true
    },
    naturalQuery: {
        type: String,
        required: [true, 'Natural query is required'],
        maxlength: [5000, 'Query cannot exceed 5000 characters']
    },
    generatedMQL: {
        type: mongoose.Schema.Types.Mixed,
        required: false
    },
    explanation: {
        type: String,
        required: false
    },
    database: {
        type: String,
        required: true
    },
    collection: {
        type: String,
        required: false
    },
    results: {
        count: {
            type: Number,
            default: 0
        },
        sample: {
            type: mongoose.Schema.Types.Mixed,
            default: []
        }
    },
    executionTime: {
        type: Number,
        default: 0,
        comment: 'Execution time in milliseconds'
    },
    success: {
        type: Boolean,
        default: true
    },
    errorMessage: {
        type: String,
        default: null
    },
    metadata: {
        llmModel: {
            type: String,
            required: false
        },
        llmProvider: {
            type: String,
            enum: ['openai', 'gemini', 'local', 'huggingface'],
            required: false
        },
        tokenUsage: {
            type: Number,
            default: 0
        },
        agentType: {
            type: String,
            default: 'mongodb_agent'
        }
    },
    timestamp: {
        type: Date,
        default: Date.now,
        index: true
    }
}, {
    timestamps: true,
    suppressReservedKeysWarning: true
});

// Index for efficient conversation retrieval
queryHistorySchema.index({ userId: 1, conversationId: 1, timestamp: -1 });

// Index for user history queries
queryHistorySchema.index({ userId: 1, timestamp: -1 });

module.exports = mongoose.model('QueryHistory', queryHistorySchema);
