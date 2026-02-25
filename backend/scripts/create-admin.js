const mongoose = require('mongoose');
const dotenv = require('dotenv');
const path = require('path');
const User = require('../models/User');
const RolePolicy = require('../models/RolePolicy');

dotenv.config({ path: path.join(__dirname, '../.env') });

const createAdmin = async () => {
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('Connected to MongoDB');

        // Get admin role policy
        const adminRole = await RolePolicy.findOne({ name: 'admin' });
        if (!adminRole) {
            console.error('Admin role policy not found. Please run seed-rbac.js first.');
            process.exit(1);
        }

        const adminData = {
            name: 'Admin User',
            email: 'ks@mail.com',
            password: 'Admin@123',
            role: 'admin',
            rolePolicy: adminRole._id
        };

        let user = await User.findOne({ email: adminData.email });
        if (user) {
            user.password = adminData.password;
            user.role = adminData.role;
            user.rolePolicy = adminData.rolePolicy;
            await user.save();
            console.log('✅ Admin user updated successfully!');
        } else {
            await User.create(adminData);
            console.log('✅ Admin user created successfully!');
        }
        console.log('Email: ks@mail.com');
        console.log('Password: Admin@123');
        process.exit(0);
    } catch (error) {
        console.error('Error creating admin:', error);
        process.exit(1);
    }
};

createAdmin();
