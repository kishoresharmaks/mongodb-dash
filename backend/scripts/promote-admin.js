const mongoose = require('mongoose');
const dotenv = require('dotenv');
const path = require('path');
const User = require('../models/User');
const RolePolicy = require('../models/RolePolicy');

// Load env vars
dotenv.config({ path: path.join(__dirname, '../.env') });

const promoteToAdmin = async () => {
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('Connected to MongoDB');

        // 1. Find or create the Manager/Admin policy
        const managerPolicy = await RolePolicy.findOne({ name: 'Manager' });

        if (!managerPolicy) {
            console.error('Manager policy not found. Run seed-rbac.js first.');
            process.exit(1);
        }

        // 2. Update the user
        const user = await User.findOneAndUpdate(
            { email: 'ks@mail.com' },
            {
                role: 'Manager',
                rolePolicy: managerPolicy._id
            },
            { new: true, upsert: true } // Create if doesn't exist
        );

        console.log('✅ User KS (ks@mail.com) has been promoted to Manager with full Admin privileges.');
        console.log('User ID:', user._id);
        console.log('Policy ID:', managerPolicy._id);

        process.exit(0);
    } catch (error) {
        console.error('Error promoting user:', error);
        process.exit(1);
    }
};

promoteToAdmin();
