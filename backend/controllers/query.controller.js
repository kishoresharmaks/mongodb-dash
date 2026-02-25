const QueryHistory = require('../models/QueryHistory');
const RolePolicy = require('../models/RolePolicy');
const nlpService = require('../services/nlp.service');
const { v4: uuidv4 } = require('uuid');

// @desc    Get a query plan (planning stage)
// @route   POST /api/query/plan
// @access  Private
exports.getQueryPlan = async (req, res) => {
    try {
        const { query, database, collection, conversationId, visualizationPreference } = req.body;

        if (!query) {
            return res.status(400).json({
                success: false,
                message: 'Please provide a query'
            });
        }

        if (query.length > 5000) {
            return res.status(400).json({
                success: false,
                message: 'Query cannot exceed 5000 characters'
            });
        }

        // Fetch previous history for this conversation to provide context
        let history = [];
        if (conversationId) {
            const previousQueries = await QueryHistory.find({
                userId: req.user.id,
                conversationId
            }).sort({ timestamp: -1 }).limit(5); // Last 5 messages

            history = previousQueries.reverse().map(q => ([
                { role: 'user', content: q.naturalQuery },
                { role: 'assistant', content: q.errorMessage ? `Error: ${q.errorMessage}` : q.explanation || `Found ${q.results.count} results.` }
            ])).flat();
        }

        // Fetch user permissions
        const user = await req.user.populate('rolePolicy');
        const permissions = user.rolePolicy?.permissions || {
            collections: [{ name: '*', operations: ['find'], fields: ['*'], restrictedFields: [] }]
        };

        const SystemConfig = require('../models/SystemConfig');
        const customPrompt = await SystemConfig.findOne({ key: 'main_system_prompt' });

        const plan = await nlpService.getPlan({
            query,
            database: database || req.user.preferences.defaultDatabase,
            collection,
            history,
            permissions,
            userRole: user.role,
            policyName: user.rolePolicy?.name,
            customSystemPrompt: customPrompt?.value || null,
            visualizationHint: visualizationPreference // NEW: Pass user's visualization preference
        });

        res.status(200).json({
            success: true,
            data: {
                conversationId: conversationId || uuidv4(),
                query,
                mql: plan.mql_query,
                explanation: plan.explanation,
                needsConfirmation: plan.needs_confirmation,
                type: plan.type,
                visualization: plan.type === 'visualization' ? {
                    chartType: plan.chart_type,
                    title: plan.title,
                    xKey: plan.x_key,
                    yKey: plan.y_key
                } : null
            }
        });
    } catch (error) {
        console.error('Query Plan Error:', error);
        res.status(500).json({
            success: false,
            message: 'Error generating query plan',
            error: error.message
        });
    }
};

// @desc    Execute a confirmed query (execution stage)
// @route   POST /api/query/execute-confirmed
// @access  Private
exports.executeConfirmedQuery = async (req, res) => {
    const startTime = Date.now();
    try {
        const { mql, naturalQuery, conversationId, database, collection, metadata } = req.body;

        if (!mql) {
            return res.status(400).json({
                success: false,
                message: 'No MQL query provided for execution'
            });
        }

        const execution = await nlpService.executeConfirmed({
            mql,
            database: database || req.user.preferences.defaultDatabase
        });

        const executionTime = Date.now() - startTime;
        const convId = conversationId || uuidv4();

        // Save to query history
        const queryHistory = await QueryHistory.create({
            userId: req.user.id,
            conversationId: convId,
            naturalQuery: naturalQuery || 'Confirmed Query',
            generatedMQL: mql,
            explanation: execution.explanation || `Found ${execution.results?.length || 0} results.`,
            database: database || req.user.preferences.defaultDatabase,
            collection: collection || mql.collection,
            results: {
                count: execution.results?.length || 0,
                sample: execution.results?.slice(0, 100) || []
            },
            executionTime,
            success: true,
            metadata: {
                llmModel: execution.metadata?.model,
                llmProvider: execution.metadata?.provider,
                agentType: 'mongodb_agent',
                visualization: metadata?.visualization
            }
        });

        res.status(200).json({
            success: true,
            data: {
                conversationId: convId,
                results: execution.results,
                resultCount: execution.results?.length || 0,
                explanation: execution.explanation,
                executionTime,
                historyId: queryHistory._id
            }
        });
    } catch (error) {
        console.error('Confirmed Execution Error:', error);
        res.status(500).json({
            success: false,
            message: 'Error executing confirmed query',
            error: error.message
        });
    }
};

// @desc    Execute natural language query
// @route   POST /api/query/execute
// @access  Private
exports.executeQuery = async (req, res) => {
    const startTime = Date.now();

    try {
        const { query, database, collection, conversationId } = req.body;

        // Validation
        if (!query) {
            return res.status(400).json({
                success: false,
                message: 'Please provide a query'
            });
        }

        if (query.length > 5000) {
            return res.status(400).json({
                success: false,
                message: 'Query cannot exceed 5000 characters'
            });
        }

        // Use provided conversationId or generate new one
        const convId = conversationId || uuidv4();

        // Call NLP service with history context
        let history = [];
        if (convId) {
            const previousQueries = await QueryHistory.find({
                userId: req.user.id,
                conversationId: convId
            }).sort({ timestamp: -1 }).limit(5);

            history = previousQueries.reverse().map(q => ([
                { role: 'user', content: q.naturalQuery },
                { role: 'assistant', content: q.errorMessage ? `Error: ${q.errorMessage}` : q.explanation || `Found ${q.results.count} results.` }
            ])).flat();
        }

        // Fetch user permissions
        const user = await req.user.populate('rolePolicy');
        const permissions = user.rolePolicy?.permissions || {
            collections: [{ name: '*', operations: ['find'], fields: ['*'], restrictedFields: [] }]
        };

        const SystemConfig = require('../models/SystemConfig');
        const customPrompt = await SystemConfig.findOne({ key: 'main_system_prompt' });

        const nlpResponse = await nlpService.translateQuery({
            query,
            database: database || req.user.preferences.defaultDatabase,
            collection,
            history,
            permissions,
            userRole: user.role,
            policyName: user.rolePolicy?.name,
            customSystemPrompt: customPrompt?.value || null
        });

        const executionTime = Date.now() - startTime;

        // Save to query history
        const queryHistory = await QueryHistory.create({
            userId: req.user.id,
            conversationId: convId,
            naturalQuery: query,
            generatedMQL: nlpResponse.mql_query,
            explanation: nlpResponse.explanation,
            database: database || req.user.preferences.defaultDatabase,
            collection: nlpResponse.collection || collection,
            results: {
                count: nlpResponse.results?.length || 0,
                sample: nlpResponse.results?.slice(0, 100) || []
            },
            executionTime,
            success: nlpResponse.success,
            errorMessage: nlpResponse.error || null,
            metadata: {
                llmModel: nlpResponse.metadata?.model,
                llmProvider: nlpResponse.metadata?.provider,
                tokenUsage: nlpResponse.metadata?.token_usage || 0,
                agentType: 'mongodb_agent'
            }
        });

        res.status(200).json({
            success: true,
            data: {
                conversationId: convId,
                query: query,
                mql: nlpResponse.mql_query,
                results: nlpResponse.results,
                resultCount: nlpResponse.results?.length || 0,
                explanation: nlpResponse.explanation,
                executionTime,
                type: nlpResponse.type,
                visualization: nlpResponse.type === 'visualization' ? {
                    chartType: nlpResponse.chart_type,
                    title: nlpResponse.title,
                    xKey: nlpResponse.x_key,
                    yKey: nlpResponse.y_key
                } : null,
                metadata: {
                    llmProvider: nlpResponse.metadata?.provider,
                    llmModel: nlpResponse.metadata?.model
                },
                historyId: queryHistory._id
            }
        });
    } catch (error) {
        const executionTime = Date.now() - startTime;

        console.error('Query Execution Error:', error);

        // Save failed query to history
        try {
            await QueryHistory.create({
                userId: req.user.id,
                conversationId: req.body.conversationId || uuidv4(),
                naturalQuery: req.body.query,
                database: req.body.database || req.user.preferences.defaultDatabase,
                executionTime,
                success: false,
                errorMessage: error.message
            });
        } catch (historyError) {
            console.error('Error saving failed query to history:', historyError);
        }

        res.status(500).json({
            success: false,
            message: 'Error executing query',
            error: error.message
        });
    }
};

// @desc    Get query history for user
// @route   GET /api/query/history
// @access  Private
exports.getHistory = async (req, res) => {
    try {
        const { limit = 50, skip = 0 } = req.query;

        const history = await QueryHistory.find({ userId: req.user.id })
            .sort({ timestamp: -1 })
            .limit(parseInt(limit))
            .skip(parseInt(skip))
            .select('-results.sample'); // Exclude large sample data

        const total = await QueryHistory.countDocuments({ userId: req.user.id });

        res.status(200).json({
            success: true,
            data: {
                history,
                pagination: {
                    total,
                    limit: parseInt(limit),
                    skip: parseInt(skip),
                    hasMore: total > parseInt(skip) + parseInt(limit)
                }
            }
        });
    } catch (error) {
        console.error('Get History Error:', error);
        res.status(500).json({
            success: false,
            message: 'Error fetching query history',
            error: error.message
        });
    }
};

// @desc    Get conversation by ID
// @route   GET /api/query/conversation/:conversationId
// @access  Private
exports.getConversation = async (req, res) => {
    try {
        const { conversationId } = req.params;

        const conversation = await QueryHistory.find({
            userId: req.user.id,
            conversationId
        }).sort({ timestamp: 1 });

        if (!conversation || conversation.length === 0) {
            return res.status(404).json({
                success: false,
                message: 'Conversation not found'
            });
        }

        res.status(200).json({
            success: true,
            data: {
                conversationId,
                queries: conversation
            }
        });
    } catch (error) {
        console.error('Get Conversation Error:', error);
        res.status(500).json({
            success: false,
            message: 'Error fetching conversation',
            error: error.message
        });
    }
};

// @desc    Delete query from history
// @route   DELETE /api/query/history/:id
// @access  Private
exports.deleteQuery = async (req, res) => {
    try {
        const query = await QueryHistory.findOne({
            _id: req.params.id,
            userId: req.user.id
        });

        if (!query) {
            return res.status(404).json({
                success: false,
                message: 'Query not found'
            });
        }

        await query.deleteOne();

        res.status(200).json({
            success: true,
            message: 'Query deleted successfully'
        });
    } catch (error) {
        console.error('Delete Query Error:', error);
        res.status(500).json({
            success: false,
            message: 'Error deleting query',
            error: error.message
        });
    }
};
