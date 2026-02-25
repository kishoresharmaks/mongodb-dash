const mongoose = require('mongoose');
require('dotenv').config();

const SystemConfig = require('./models/SystemConfig');

async function fixCustomPrompt() {
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('✅ Connected to MongoDB\n');

        // Option 1: Delete the broken custom prompt (recommended for now)
        console.log('🗑️  Deleting broken custom prompt from database...');
        const deleteResult = await SystemConfig.deleteOne({ key: 'main_system_prompt' });

        if (deleteResult.deletedCount > 0) {
            console.log('✅ Successfully deleted custom prompt');
            console.log('   The system will now use the default prompt template from mongodb_agent.py');
        } else {
            console.log('ℹ️  No custom prompt found in database (already using default)');
        }

        console.log('\n📝 Summary:');
        console.log('   - Custom prompt: REMOVED');
        console.log('   - System will use: Default template from code');
        console.log('   - This ensures {natural_query} placeholder is always present');

        await mongoose.connection.close();
        console.log('\n✅ Done!');
    } catch (error) {
        console.error('❌ Error:', error);
        process.exit(1);
    }
}

fixCustomPrompt();
