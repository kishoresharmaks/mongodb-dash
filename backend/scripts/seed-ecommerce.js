const mongoose = require('mongoose');
const { faker } = require('@faker-js/faker');
const dotenv = require('dotenv');
const path = require('path');

// Load env vars
dotenv.config({ path: path.join(__dirname, '../.env') });

const MONGODB_URI = process.env.MONGODB_URI;

// Define Schemas
const CategorySchema = new mongoose.Schema({
    name: String,
    description: String,
    slug: String
});

const ProductSchema = new mongoose.Schema({
    name: String,
    description: String,
    price: Number,
    category: { type: mongoose.Schema.Types.ObjectId, ref: 'Category' },
    stock: Number,
    rating: Number,
    reviews_count: Number,
    tags: [String],
    created_at: Date
});

const CustomerSchema = new mongoose.Schema({
    first_name: String,
    last_name: String,
    email: String,
    address: {
        street: String,
        city: String,
        state: String,
        zip: String,
        country: String
    },
    joined_at: Date
});

const OrderSchema = new mongoose.Schema({
    user: { type: mongoose.Schema.Types.ObjectId, ref: 'Customer' },
    items: [{
        product: { type: mongoose.Schema.Types.ObjectId, ref: 'Product' },
        quantity: Number,
        price: Number
    }],
    total_amount: Number,
    status: { type: String, enum: ['pending', 'shipped', 'delivered', 'cancelled'], default: 'pending' },
    order_date: Date
});

const Category = mongoose.model('Category', CategorySchema);
const Product = mongoose.model('Product', ProductSchema);
const Customer = mongoose.model('Customer', CustomerSchema);
const Order = mongoose.model('Order', OrderSchema);

const seedEcommerce = async () => {
    try {
        console.log('Connecting to MongoDB...');
        await mongoose.connect(MONGODB_URI);
        console.log('Connected successfully.');

        // Clear existing data
        console.log('Clearing existing data...');
        await Category.deleteMany({});
        await Product.deleteMany({});
        await Customer.deleteMany({});
        await Order.deleteMany({});

        // Generate Categories
        console.log('Generating categories...');
        const categories = [];
        const categoryNames = ['Electronics', 'Clothing', 'Home & Kitchen', 'Books', 'Toys', 'Sports', 'Beauty', 'Health', 'Automotive', 'Jewelry'];

        for (const name of categoryNames) {
            categories.push({
                name,
                description: faker.commerce.productDescription(),
                slug: name.toLowerCase().replace(/ /g, '-')
            });
        }
        const createdCategories = await Category.insertMany(categories);

        // Generate Products
        console.log('Generating products...');
        const products = [];
        for (let i = 0; i < 500; i++) {
            const category = createdCategories[Math.floor(Math.random() * createdCategories.length)];
            products.push({
                name: faker.commerce.productName(),
                description: faker.commerce.productDescription(),
                price: parseFloat(faker.commerce.price({ min: 10, max: 1000 })),
                category: category._id,
                stock: faker.number.int({ min: 0, max: 200 }),
                rating: faker.number.float({ min: 1, max: 5, multipleOf: 0.1 }),
                reviews_count: faker.number.int({ min: 0, max: 1000 }),
                tags: [faker.commerce.productAdjective(), faker.commerce.productAdjective()],
                created_at: faker.date.past()
            });
        }
        const createdProducts = await Product.insertMany(products);

        // Generate Customers
        console.log('Generating customers...');
        const customers = [];
        for (let i = 0; i < 200; i++) {
            customers.push({
                first_name: faker.person.firstName(),
                last_name: faker.person.lastName(),
                email: faker.internet.email(),
                address: {
                    street: faker.location.streetAddress(),
                    city: faker.location.city(),
                    state: faker.location.state(),
                    zip: faker.location.zipCode(),
                    country: faker.location.country()
                },
                joined_at: faker.date.past()
            });
        }
        const createdCustomers = await Customer.insertMany(customers);

        // Generate Orders
        console.log('Generating orders...');
        const orders = [];
        for (let i = 0; i < 1000; i++) {
            const user = createdCustomers[Math.floor(Math.random() * createdCustomers.length)];
            const orderItems = [];
            const itemCount = faker.number.int({ min: 1, max: 5 });
            let totalAmount = 0;

            for (let j = 0; j < itemCount; j++) {
                const product = createdProducts[Math.floor(Math.random() * createdProducts.length)];
                const quantity = faker.number.int({ min: 1, max: 3 });
                const price = product.price;

                orderItems.push({
                    product: product._id,
                    quantity,
                    price
                });
                totalAmount += price * quantity;
            }

            orders.push({
                user: user._id,
                items: orderItems,
                total_amount: Math.round(totalAmount * 100) / 100,
                status: faker.helpers.arrayElement(['pending', 'shipped', 'delivered', 'cancelled']),
                order_date: faker.date.recent({ days: 90 })
            });
        }
        await Order.insertMany(orders);

        console.log('✅ E-commerce data seeded successfully!');
        console.log(`- Categories: ${createdCategories.length}`);
        console.log(`- Products: ${createdProducts.length}`);
        console.log(`- Customers: ${createdCustomers.length}`);
        console.log(`- Orders: 1000`);

        process.exit(0);
    } catch (error) {
        console.error('Error seeding e-commerce data:', error);
        process.exit(1);
    }
};

seedEcommerce();
