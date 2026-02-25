const SystemConfig = require('../models/SystemConfig');

// @desc    Get system configuration
// @route   GET /api/admin/config/:key
// @access  Private/Admin
exports.getConfig = async (req, res) => {
    try {
        const { key } = req.params;
        let config = await SystemConfig.findOne({ key });

        // If it doesn't exist, return empty or default
        if (!config) {
            return res.status(200).json({
                success: true,
                data: { key, value: "" }
            });
        }

        res.status(200).json({
            success: true,
            data: config
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: 'Error fetching config',
            error: error.message
        });
    }
};

// @desc    Update system configuration
// @route   POST /api/admin/config
// @access  Private/Admin
exports.updateConfig = async (req, res) => {
    try {
        const { key, value, description } = req.body;

        if (!key || value === undefined) {
            return res.status(400).json({
                success: false,
                message: 'Please provide key and value'
            });
        }

        let config = await SystemConfig.findOne({ key });

        if (config) {
            config.value = value;
            if (description) config.description = description;
            config.lastUpdatedBy = req.user.id;
            config.updatedAt = Date.now();
            await config.save();
        } else {
            config = await SystemConfig.create({
                key,
                value,
                description,
                lastUpdatedBy: req.user.id
            });
        }

        res.status(200).json({
            success: true,
            data: config
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: 'Error updating config',
            error: error.message
        });
    }
};
// @desc    Get all available collections directly from MongoDB
// @route   GET /api/admin/metadata/collections
// @access  Private/Admin
exports.getMetadataCollections = async (req, res) => {
    try {
        const mongoose = require('mongoose');

        // Get all collections in the current database
        const collections = await mongoose.connection.db.listCollections().toArray();
        const collectionNames = collections
            .map(c => c.name)
            .filter(name => !name.startsWith('system.')) // Exclude MongoDB system collections
            .sort();

        res.status(200).json({
            success: true,
            data: collectionNames
        });
    } catch (error) {
        console.error('Metadata Fetch Error:', error.message);
        res.status(500).json({
            success: false,
            message: 'Error fetching database metadata',
            error: error.message
        });
    }
};

// @desc    Reset system configuration to default
// @route   POST /api/admin/config/reset
// @access  Private/Admin
exports.resetConfig = async (req, res) => {
    try {
        const { key } = req.body;

        if (key === 'main_system_prompt') {
            const defaultPrompt = `You are a MongoDB query expert and assistant. 

{permission_text}
{history_text}

TASK 1: CLASSIFY THE QUERY
Determine the intent. PRIORITY: Visualization > Database > Conversational.

1. VISUALIZATION (When user asks for a chart, graph, or distribution):
{
    "type": "visualization",
    "chart_type": "bar",
    "title": "Descriptive Chart Title",
    "x_key": "label",
    "y_key": "value",
    "explanation": "Technical overview. [EXPECTED RESULTS]: Describe the data being plotted.",
    "mql": {
        "collection": "collection_name", 
        "operation": "aggregate",
        "pipeline": [
            { "$lookup": { "from": "related_collection", "localField": "reference_field", "foreignField": "_id", "as": "joined_data" } },
            { "$unwind": { "path": "$joined_data", "preserveNullAndEmptyArrays": true } },
            { "$group": { "_id": "$joined_data.name", "value": { "$sum": 1 } } },
            { "$project": { "_id": 0, "label": "$_id", "value": 1 } },
            { "$sort": { "value": -1 } },
            { "$limit": 10 }
        ]
    }
}
CRITICAL FOR VISUALIZATIONS:
- ALWAYS use "operation": "aggregate"
- If grouping by a field that is an ObjectId reference (like category, user, product), you MUST use $lookup to join with the referenced collection first
- Example: If products have "category" as ObjectId, use $lookup to join with "categories" collection, then group by the category name
- ALWAYS include a final "$project" stage that maps X-axis to "label" and Y-axis to "value"
- The "label" field must contain human-readable text (names, not IDs)

2. DATABASE QUERY (Data retrieval or modification):
{
    "type": "database",
    "explanation": "Technical breakdown. [EXPECTED RESULTS]: Describe the format and limit.",
    "mql": {
        "collection": "collection_name",
        "operation": "find",
        "query": {filter},
        "projection": {fields},
        "sort": {sort_fields},
        "limit": 20
    }
}

3. CONVERSATIONAL:
{
    "type": "conversational",
    "response": "Your structured Markdown response."
}

MQL POWER RULES:
- Use dot notation for nested fields.
- For text search, use { "$regex": "...", "$options": "i" }.
- Numeric fields should NOT be quoted.
- ALWAYS use $project in aggregate to rename fields to 'label' and 'value' for charts.

Database: {database_name}
Available Collections: {collections_list}
Current Context: {current_collection} ({fields_list})

Result (JSON Only):`;

            await SystemConfig.findOneAndUpdate(
                { key },
                {
                    value: defaultPrompt,
                    description: 'Main AI assistant system instructions',
                    lastUpdatedBy: req.user.id,
                    updatedAt: Date.now()
                },
                { upsert: true }
            );

            return res.status(200).json({
                success: true,
                message: 'Configuration reset to system default'
            });
        }

        res.status(400).json({
            success: false,
            message: 'Invalid key for reset'
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: 'Error resetting config',
            error: error.message
        });
    }
};
