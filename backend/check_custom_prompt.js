const mongoose = require('mongoose');
require('dotenv').config();

const SystemConfig = require('./models/SystemConfig');

async function checkCustomPrompt() {
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('Connected to MongoDB');

        const customPrompt = await SystemConfig.findOne({ key: 'main_system_prompt' });

        if (customPrompt) {
            console.log('\n📝 Custom System Prompt Found:');
            console.log('='.repeat(60));
            console.log(customPrompt.value);
            console.log('='.repeat(60));
            console.log(`\nLength: ${customPrompt.value.length} characters`);
            console.log(`Contains {natural_query}: ${customPrompt.value.includes('{natural_query}')}`);
        } else {
            console.log('❌ No custom system prompt found in database');
        }

        await mongoose.connection.close();
    } catch (error) {
        console.error('Error:', error);
        process.exit(1);
    }
}

checkCustomPrompt();
