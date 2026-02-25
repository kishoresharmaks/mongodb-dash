const mongoose = require('mongoose');
require('dotenv').config();
const RolePolicy = require('./models/RolePolicy');
const User = require('./models/User');

const seedRBAC = async () => {
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('🌱 Connected to MongoDB for seeding RBAC...');

        // 1. Create Analyst Role
        const analyst = await RolePolicy.findOneAndUpdate(
            { name: 'Analyst' },
            {
                description: 'Can query all collections but cannot see salaries or PII.',
                permissions: {
                    collections: [{
                        name: '*',
                        operations: ['find', 'aggregate'],
                        fields: ['*'],
                        restrictedFields: ['salary', 'pii', 'password', 'email']
                    }],
                    maxLimit: 100
                },
                isDefault: true
            },
            { upsert: true, new: true }
        );
        console.log('✅ Analyst role seeded');

        // 2. Create Manager Role
        const manager = await RolePolicy.findOneAndUpdate(
            { name: 'Manager' },
            {
                description: 'Full access to all collections and fields.',
                permissions: {
                    collections: [{
                        name: '*',
                        operations: ['find', 'aggregate', 'insert', 'update', 'delete'],
                        fields: ['*'],
                        restrictedFields: []
                    }],
                    maxLimit: 1000
                }
            },
            { upsert: true, new: true }
        );
        console.log('✅ Manager role seeded');

        // 2.5 Create Admin Role
        const adminRole = await RolePolicy.findOneAndUpdate(
            { name: 'admin' },
            {
                description: 'Full administrative access.',
                permissions: {
                    collections: [{
                        name: '*',
                        operations: ['find', 'aggregate', 'insert', 'update', 'delete'],
                        fields: ['*'],
                        restrictedFields: []
                    }],
                    maxLimit: 10000
                }
            },
            { upsert: true, new: true }
        );
        console.log('✅ Admin role seeded');

        // 3. Update existing users to default role
        await User.updateMany(
            { rolePolicy: { $exists: false } },
            { rolePolicy: analyst._id, role: 'Analyst' }
        );
        console.log('✅ Existing users updated to Analyst role');

        process.exit(0);
    } catch (err) {
        console.error('❌ Seeding failed:', err);
        process.exit(1);
    }
};

seedRBAC();
