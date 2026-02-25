const mongoose = require('mongoose');
require('dotenv').config();
const User = require('./models/User');

const setAdmin = async (email) => {
    if (!email) {
        console.error('❌ Please provide an email: node set-admin.js email@example.com');
        process.exit(1);
    }

    try {
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('🌱 Connected to MongoDB...');

        const user = await User.findOneAndUpdate(
            { email: email.toLowerCase() },
            { role: 'admin' },
            { new: true }
        );

        if (!user) {
            console.error(`❌ User with email ${email} not found.`);
        } else {
            console.log(`✅ User ${user.name} (${user.email}) is now an ADMIN.`);
            console.log('🚀 You can now access the Admin Portal at /admin after re-logging.');
        }

        process.exit(0);
    } catch (err) {
        console.error('❌ Error:', err);
        process.exit(1);
    }
};

const emailArg = process.argv[2];
setAdmin(emailArg);
