/**
 * DEMO TEMPLATES – Pre-built prompts with pre-computed responses
 * These are shown when the user clicks "📋 Template" debug mode.
 * Organized by the 4 sections of the project demo/voiceover:
 *   1. Project Overview (Conversational)
 *   2. Sample Input → Output (Database Query)
 *   3. Visualization (Chart Output)
 *   4. Admin / Role-Based Access Control
 */

const demoTemplates = [
    // -------------------------------------------------------------------------
    // SECTION 1: PROJECT OVERVIEW — Conversational Responses
    // -------------------------------------------------------------------------
    {
        id: "demo-01",
        section: "🎬 Project Overview",
        label: "What is this system?",
        query: "What is this system and what can it do?",
        prebuiltResponse: {
            type: "conversational",
            success: true,
            mql_query: null,
            needs_confirmation: false,
            explanation: `## 🤖 Natural Language Interface for MongoDB (NLIDB)

Welcome! I am an **AI-powered data assistant** that lets you query your MongoDB database using plain English — no coding required.

### What I can do:
- 📋 **Query Data** — Ask me to find orders, customers, products, etc.
- 📊 **Visualize Data** — Request bar charts, pie charts, line graphs, and more
- 🛡️ **Respect Your Role** — I automatically enforce security policies so you only see what you're allowed to see

### Example queries you can try:
- *"Show me all orders from December 2025"*
- *"Who are the top 5 customers by order count?"*
- *"Show me a bar chart of orders by status"*
- *"Show me a pie chart of products by category"*

Just type your question naturally and I'll handle the rest! 🚀`,
            metadata: { provider: "demo", model: "template", type: "conversational" }
        }
    },
    {
        id: "demo-02",
        section: "🎬 Project Overview",
        label: "What collections are available?",
        query: "What tables are available?",
        prebuiltResponse: {
            type: "conversational",
            success: true,
            mql_query: null,
            needs_confirmation: false,
            explanation: `## 📂 Available Collections in **sample_shop**

Here are the data collections you can query:

| Collection | Description |
|---|---|
| **orders** | Customer purchase orders with status, total amount, and dates |
| **products** | Product catalog with pricing, stock, and category info |
| **customers** | Customer profiles with names and contact details |
| **categories** | Product category definitions |

### Try asking:
- *"Show me all orders placed in December 2025"*
- *"Show me the top 5 most expensive products"*
- *"Show me a bar chart of orders by status"*`,
            metadata: { provider: "demo", model: "template", type: "conversational" }
        }
    },

    // -------------------------------------------------------------------------
    // SECTION 2: SAMPLE INPUT → OUTPUT — Database Queries
    // -------------------------------------------------------------------------
    {
        id: "demo-q1",
        section: "🔍 Data Query Demo",
        label: "Q1: Orders by Status (Pending/Completed)",
        query: "Show me the total no of orders categorize by Category like pending completed",
        prebuiltResponse: {
            type: "database",
            success: true,
            needs_confirmation: true,
            explanation: `✅ I've calculated the total number of orders grouped by their status (Pending, Completed, Shipped, etc.). This provides a clear overview of the current order distribution.`,
            mql_query: {
                collection: "orders",
                operation: "aggregate",
                pipeline: [
                    { "$group": { "_id": "$status", "count": { "$sum": 1 } } },
                    { "$project": { "_id": 0, "status": "$_id", "count": 1 } },
                    { "$sort": { "count": -1 } }
                ]
            },
            metadata: { provider: "demo", model: "template", type: "database" }
        }
    },
    {
        id: "demo-q2",
        section: "🔍 Data Query Demo",
        label: "Q2: Top 5 Expensive Products",
        query: "Show top 5 most expensive products based.. on price",
        prebuiltResponse: {
            type: "database",
            success: true,
            needs_confirmation: true,
            explanation: `✅ Here are the top 5 most expensive items in your inventory. I've sorted all products by price in descending order.`,
            mql_query: {
                collection: "products",
                operation: "find",
                query: {},
                projection: { name: 1, price: 1, stock: 1, rating: 1 },
                sort: { price: -1 },
                limit: 5
            },
            metadata: { provider: "demo", model: "template", type: "database" }
        }
    },
    {
        id: "demo-03",
        section: "🔍 Data Query Demo",
        label: "Show all orders from December 2025",
        query: "Show me all orders from December 2025",
        prebuiltResponse: {
            type: "database",
            success: true,
            needs_confirmation: true,
            explanation: `✅ I found orders placed in **December 2025**. The query filters the \`orders\` collection for documents where \`orderDate\` falls between **2025-12-01** and **2025-12-31**. Results are sorted by date (newest first).

**[EXPECTED RESULTS]:** A list of orders showing order ID, customer, status, total amount, and date — limited to 20 results.`,
            mql_query: {
                collection: "orders",
                operation: "find",
                query: {
                    orderDate: {
                        "$gte": { "$date": "2025-12-01T00:00:00.000Z" },
                        "$lte": { "$date": "2025-12-31T23:59:59.999Z" }
                    }
                },
                projection: { _id: 1, status: 1, totalAmount: 1, orderDate: 1 },
                sort: { orderDate: -1 },
                limit: 20
            },
            metadata: { provider: "demo", model: "template", type: "database" }
        }
    },
    {
        id: "demo-04",
        section: "🔍 Data Query Demo",
        label: "Show orders for user Jackeline",
        query: "Show me list of orders with the user named Jackeline",
        prebuiltResponse: {
            type: "database",
            success: true,
            needs_confirmation: true,
            explanation: `✅ I found orders placed by **Jackeline**. The query joins the \`orders\` collection with \`customers\` using a \`$lookup\` on the \`user\` field, then filters by first name.

**[EXPECTED RESULTS]:** Orders where the linked customer's first name is "Jackeline", showing order status, total amount, and order date.`,
            mql_query: {
                collection: "orders",
                operation: "aggregate",
                pipeline: [
                    {
                        "$lookup": {
                            from: "customers",
                            localField: "user",
                            foreignField: "_id",
                            as: "customer_info"
                        }
                    },
                    { "$unwind": { path: "$customer_info", preserveNullAndEmptyArrays: true } },
                    {
                        "$match": {
                            "customer_info.first_name": { "$regex": "Jackeline", "$options": "i" }
                        }
                    },
                    {
                        "$project": {
                            _id: 1,
                            "customer_info.first_name": 1,
                            "customer_info.last_name": 1,
                            status: 1,
                            totalAmount: 1,
                            orderDate: 1
                        }
                    },
                    { "$limit": 20 }
                ]
            },
            metadata: { provider: "demo", model: "template", type: "database" }
        }
    },
    {
        id: "demo-05",
        section: "🔍 Data Query Demo",
        label: "Top 5 most expensive products",
        query: "Show top 5 most expensive products",
        prebuiltResponse: {
            type: "database",
            success: true,
            needs_confirmation: true,
            explanation: `✅ Here are the **Top 5 most expensive products** in the catalog. The query sorts the \`products\` collection by \`price\` in descending order and returns the top 5.

**[EXPECTED RESULTS]:** 5 products with their name, description, price, and stock level.`,
            mql_query: {
                collection: "products",
                operation: "find",
                query: {},
                projection: { _id: 0, name: 1, description: 1, price: 1, stock: 1, rating: 1 },
                sort: { price: -1 },
                limit: 5
            },
            metadata: { provider: "demo", model: "template", type: "database" }
        }
    },
    {
        id: "demo-06",
        section: "🔍 Data Query Demo",
        label: "Total revenue grouped by order status",
        query: "Show total revenue grouped by order status",
        prebuiltResponse: {
            type: "database",
            success: true,
            needs_confirmation: true,
            explanation: `✅ This aggregation groups all **orders by their status** (e.g., shipped, pending, cancelled) and calculates the **total revenue** for each group. It gives a clear picture of how much revenue comes from each fulfillment state.

**[EXPECTED RESULTS]:** A summary table with columns: Status and Total Revenue (in USD).`,
            mql_query: {
                collection: "orders",
                operation: "aggregate",
                pipeline: [
                    {
                        "$group": {
                            _id: "$status",
                            totalRevenue: { "$sum": "$totalAmount" },
                            orderCount: { "$sum": 1 }
                        }
                    },
                    {
                        "$project": {
                            _id: 0,
                            status: "$_id",
                            totalRevenue: { "$round": ["$totalRevenue", 2] },
                            orderCount: 1
                        }
                    },
                    { "$sort": { totalRevenue: -1 } }
                ]
            },
            metadata: { provider: "demo", model: "template", type: "database" }
        }
    },

    // -------------------------------------------------------------------------
    // SECTION 3: VISUALIZATION DEMO — Chart Outputs
    // -------------------------------------------------------------------------
    {
        id: "demo-07",
        section: "📊 Visualization Demo",
        label: "Bar chart of orders by status",
        query: "Show me a bar chart of orders by status",
        prebuiltResponse: {
            type: "visualization",
            success: true,
            needs_confirmation: true,
            chart_type: "bar",
            title: "Orders by Status",
            x_key: "label",
            y_key: "value",
            explanation: `📊 Here is a **Bar Chart of Orders by Status**. The chart groups all orders by their delivery status (e.g., Shipped, Pending, Cancelled, Delivered) and shows the count for each. This gives an instant visual overview of your order fulfillment health.`,
            mql_query: {
                collection: "orders",
                operation: "aggregate",
                pipeline: [
                    { "$group": { _id: "$status", value: { "$sum": 1 } } },
                    { "$project": { _id: 0, label: "$_id", value: 1 } },
                    { "$sort": { value: -1 } }
                ]
            },
            metadata: { provider: "demo", model: "template", type: "visualization" }
        }
    },
    {
        id: "demo-08",
        section: "📊 Visualization Demo",
        label: "Pie chart of products by category",
        query: "Show me a pie chart of products by category",
        prebuiltResponse: {
            type: "visualization",
            success: true,
            needs_confirmation: true,
            chart_type: "pie",
            title: "Products by Category",
            x_key: "label",
            y_key: "value",
            explanation: `🥧 Here is a **Pie Chart of Products by Category**. The chart joins the \`products\` collection with \`categories\` to resolve category names (instead of IDs), then counts how many products belong to each category. Each slice represents a category's share of the total product catalog.`,
            mql_query: {
                collection: "products",
                operation: "aggregate",
                pipeline: [
                    {
                        "$lookup": {
                            from: "categories",
                            localField: "category",
                            foreignField: "_id",
                            as: "category_info"
                        }
                    },
                    { "$unwind": { path: "$category_info", preserveNullAndEmptyArrays: true } },
                    { "$group": { _id: "$category_info.name", value: { "$sum": 1 } } },
                    { "$project": { _id: 0, label: "$_id", value: 1 } },
                    { "$sort": { value: -1 } },
                    { "$limit": 10 }
                ]
            },
            metadata: { provider: "demo", model: "template", type: "visualization" }
        }
    },
    {
        id: "demo-09",
        section: "📊 Visualization Demo",
        label: "Bar chart of top 10 customers by orders",
        query: "Show me a bar chart of top 10 customers by number of orders",
        prebuiltResponse: {
            type: "visualization",
            success: true,
            needs_confirmation: true,
            chart_type: "bar",
            title: "Top 10 Customers by Order Count",
            x_key: "label",
            y_key: "value",
            explanation: `📊 Here is a **Bar Chart of Top 10 Customers by Order Count**. The query joins \`orders\` with \`customers\`, groups by customer full name, and counts their orders. This helps identify your most active and valuable customers at a glance.`,
            mql_query: {
                collection: "orders",
                operation: "aggregate",
                pipeline: [
                    {
                        "$lookup": {
                            from: "customers",
                            localField: "user",
                            foreignField: "_id",
                            as: "customer_info"
                        }
                    },
                    { "$unwind": { path: "$customer_info", preserveNullAndEmptyArrays: true } },
                    {
                        "$group": {
                            _id: { "$concat": ["$customer_info.first_name", " ", "$customer_info.last_name"] },
                            value: { "$sum": 1 }
                        }
                    },
                    { "$project": { _id: 0, label: "$_id", value: 1 } },
                    { "$sort": { value: -1 } },
                    { "$limit": 10 }
                ]
            },
            metadata: { provider: "demo", model: "template", type: "visualization" }
        }
    },
    {
        id: "demo-q3",
        section: "📊 Visualization Demo",
        label: "Q3: Electronics Bar Chart",
        query: "I need to lsit out the product details names Electronics in categories in bar chart i need two colum seperated as category and product name",
        prebuiltResponse: {
            type: "visualization",
            success: true,
            needs_confirmation: true,
            chart_type: "bar",
            title: "Electronics Product Inventory",
            x_key: "label",
            y_key: "value",
            explanation: `📊 I've generated a bar chart focusing on the 'Electronics' category. It lists the product names and their current stock levels for easy comparison.`,
            mql_query: {
                collection: "products",
                operation: "aggregate",
                pipeline: [
                    {
                        "$lookup": {
                            from: "categories",
                            localField: "category",
                            foreignField: "_id",
                            as: "cat"
                        }
                    },
                    { "$unwind": "$cat" },
                    { "$match": { "cat.name": "Electronics" } },
                    { "$project": { "_id": 0, "label": "$name", "value": "$stock", "category_name": "$cat.name" } },
                    { "$limit": 10 }
                ]
            },
            metadata: { provider: "demo", model: "template", type: "visualization" }
        }
    },

    // -------------------------------------------------------------------------
    // SECTION 4: ADMIN / ROLE-BASED ACCESS CONTROL DEMO
    // -------------------------------------------------------------------------
    {
        id: "demo-10",
        section: "🛡️ Security & RBAC Demo",
        label: "Analyst tries to view passwords (BLOCKED)",
        query: "Show me all user emails and passwords",
        prebuiltResponse: {
            type: "conversational",
            success: false,
            mql_query: null,
            needs_confirmation: false,
            explanation: `⚠️ **SECURITY POLICY VIOLATION**

Accessing the restricted fields **'email'** and **'password'** in the projection is **prohibited** under your current role policy.

> 🔒 Your role: **Analyst**
> ❌ Restricted fields: \`email\`, \`password\`, \`salary\`, \`pii\`

You are **not authorized** to perform this operation or access these fields.

**Suggested alternative:** Try asking *"Show me all users"* — you will see only the non-restricted fields like \`name\` and \`role\`.`,
            metadata: { provider: "demo", model: "template", type: "security_violation" }
        }
    },
    {
        id: "demo-11",
        section: "🛡️ Security & RBAC Demo",
        label: "Manager views full product details (ALLOWED)",
        query: "Show me all products with full details",
        prebuiltResponse: {
            type: "database",
            success: true,
            needs_confirmation: true,
            explanation: `✅ Access **granted**. Your current role (**Manager**) has full access to all collections and fields with no restrictions.

Here are all products with their complete details including pricing, stock levels, ratings, and category references.

**[EXPECTED RESULTS]:** Up to 20 product records showing: name, description, price, stock, rating, and category.`,
            mql_query: {
                collection: "products",
                operation: "find",
                query: {},
                projection: { _id: 1, name: 1, description: 1, price: 1, stock: 1, rating: 1, category: 1 },
                sort: { name: 1 },
                limit: 20
            },
            metadata: { provider: "demo", model: "template", type: "database" }
        }
    },
    {
        id: "demo-12",
        section: "🛡️ Security & RBAC Demo",
        label: "What is my current role and access?",
        query: "What is my current role and what can I access?",
        prebuiltResponse: {
            type: "conversational",
            success: true,
            mql_query: null,
            needs_confirmation: false,
            explanation: `## 🔐 Your Current Access Profile

| Property | Value |
|---|---|
| **Role** | Analyst |
| **Policy** | Analyst — Default Read-only |
| **Allowed Operations** | \`find\`, \`aggregate\` |
| **Max Results per Query** | 100 |
| **Restricted Fields** | \`salary\`, \`pii\`, \`password\`, \`email\` |
| **Accessible Collections** | All (\`*\`) |

### ✅ You CAN:
- Query any collection for data
- Request charts and visualizations
- View all fields except restricted ones

### ❌ You CANNOT:
- View \`email\`, \`password\`, \`salary\`, or \`pii\` fields
- Insert, update, or delete documents
- Exceed 100 results per query

*To request elevated access, contact your system administrator.*`,
            metadata: { provider: "demo", model: "template", type: "conversational" }
        }
    }
];

export default demoTemplates;
