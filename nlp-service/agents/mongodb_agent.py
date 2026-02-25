from typing import Dict, Any, List, Optional
from pymongo import MongoClient
from langchain_core.messages import HumanMessage, SystemMessage
import json
import re
from bson import ObjectId
import time

from services.llm_service import create_llm
from utils.validators import validate_mql_safety
from utils.query_optimizer import optimize_mql, add_query_hints
from utils.nlp_processor import processor

class MongoDBNLAgent:
    """
    Natural Language Agent for MongoDB queries.
    Supports multiple LLM providers (OpenAI, Gemini, Local).
    """
    
    def __init__(self, connection_string: str, database_name: str):
        """
        Initialize MongoDB NL Agent.
        
        Args:
            connection_string: MongoDB Atlas connection string
            database_name: Name of the database to query
        """
        print(f"🔧 Initializing MongoDB NL Agent for database: {database_name}")
        
        # Initialize LLM
        self.llm, self.llm_metadata = create_llm()
        
        # Connect to MongoDB
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.database_name = database_name
        
        print(f"✅ Connected to MongoDB database: {database_name}")
        
        # Get collection names for context
        self.collections = self.db.list_collection_names()
        print(f"📚 Available collections: {', '.join(self.collections)}")
        
        # Initialize schema cache and preload
        self.schema_cache = {}
        self._preload_schemas()
    
    def _fix_mql(self, mql: Dict[str, Any]) -> Dict[str, Any]:
        """Fix common LLM mistakes in MQL structure"""
        if not isinstance(mql, dict):
            return mql
            
        print("🛠️ Sanitizing MQL structure...")
        
        # 1. Handle keys starting with $ at top level (e.g., $sort -> sort)
        fix_keys = {
            "$sort": "sort",
            "$limit": "limit",
            "$projection": "projection",
            "$project": "projection",
            "$filter": "query",
            "$query": "query",
            "$collection": "collection"
        }
        
        for old_key, new_key in fix_keys.items():
            if old_key in mql and new_key not in mql:
                mql[new_key] = mql.pop(old_key)
        
        operation = mql.get("operation", "find")
        query = mql.get("query", {})
        
        # 2. Fix Mixed Projection Issues (Cannot mix 1 and 0 except for _id)
        projection = mql.get("projection")
        if isinstance(projection, dict):
            inclusions = [k for k, v in projection.items() if v == 1 and k != "_id"]
            exclusions = [k for k, v in projection.items() if v == 0 and k != "_id"]
            
            if inclusions and exclusions:
                print(f"⚠️ Fixed mixed projection: Removed exclusions {exclusions}")
                # If there are inclusions, remove all exclusions (except potentially _id which is allowed)
                new_proj = {k: v for k, v in projection.items() if v == 1 or k == "_id"}
                mql["projection"] = new_proj
        
        # 2. If 'query' contains aggregation operators, move them out
        if isinstance(query, dict):
            # Check for accidental nesting or aggregation operators in find filter
            for op in ["$sort", "$limit", "$project", "$projection"]:
                if op in query:
                    clean_name = fix_keys.get(op, op.replace("$", ""))
                    if clean_name == "project": clean_name = "projection"
                    
                    if clean_name not in mql:
                        mql[clean_name] = query.pop(op)
                    else:
                        query.pop(op)
            
            # If query is just a single key '$match', it's actually just the filter
            if len(query) == 1 and "$match" in query:
                mql["query"] = query["$match"]
            
            # If it has other top-level aggregation ops but operation is 'find'
            if any(op in query for op in ["$group", "$unwind", "$lookup"]) and operation == "find":
                mql["operation"] = "aggregate"
                # If it's switched to aggregate, the query should be wrapped in $match if not already
                if "pipeline" not in mql:
                     mql["pipeline"] = [{"$match": query}]
        
        return mql

    def _get_collection_schema(self, collection_name: str, sample_size: int = 3, use_cache: bool = True) -> Dict[str, Any]:
        """Get schema information from a collection with field types and sample values"""
        # Check cache first
        if use_cache and collection_name in self.schema_cache:
            return self.schema_cache[collection_name]
            
        try:
            collection = self.db[collection_name]
            sample_docs = list(collection.find().limit(sample_size))
            
            if not sample_docs:
                schema = {"fields": [], "typed_fields": [], "sample": [], "count": 0}
                if use_cache: self.schema_cache[collection_name] = schema
                return schema
            
            # Extract field names from first document
            fields = list(sample_docs[0].keys()) if sample_docs else []
            
            # Build typed field info with sample values
            typed_fields = []
            for field in fields:
                sample_values = []
                field_type = "unknown"
                sub_fields = []  # For array<object> fields, store sub-field names
                is_array = False
                for doc in sample_docs:
                    val = doc.get(field)
                    if val is not None:
                        if isinstance(val, list):
                            is_array = True
                            field_type = "array"
                            # Get type of array elements
                            if val and isinstance(val[0], dict):
                                field_type = "array<object>"
                                # Extract sub-field names from array elements
                                if not sub_fields:
                                    sub_fields = list(val[0].keys())
                            elif val:
                                field_type = f"array<{type(val[0]).__name__}>"
                                if not sample_values:
                                    sample_values = [str(v) for v in val[:2] if len(str(v)) < 60]
                        elif isinstance(val, dict):
                            field_type = "object"
                        elif isinstance(val, bool):
                            field_type = "boolean"
                        elif isinstance(val, int):
                            field_type = "int"
                        elif isinstance(val, float):
                            field_type = "float"
                        elif hasattr(val, 'generation_time'):  # ObjectId
                            field_type = "ObjectId"
                        elif hasattr(val, 'isoformat'):  # datetime
                            field_type = "datetime"
                            sample_values.append(val.isoformat())
                            continue
                        else:
                            field_type = "string"
                        
                        str_val = str(val)
                        if not is_array and len(str_val) < 60 and str_val not in sample_values:
                            sample_values.append(str_val)
                
                typed_fields.append({
                    "field": field,
                    "type": field_type,
                    "sample_values": sample_values[:3],  # Max 3 samples
                    "nullable": any(doc.get(field) is None for doc in sample_docs),
                    "sub_fields": sub_fields  # Sub-fields for array<object>
                })
            
            # Use estimated count for speed on large collections
            try:
                count = collection.estimated_document_count()
            except:
                count = collection.count_documents({}, maxTimeMS=1000)
            
            schema = {
                "fields": fields,
                "typed_fields": typed_fields,
                "sample": sample_docs,
                "count": count
            }
            
            if use_cache: self.schema_cache[collection_name] = schema
            return schema
        except Exception as e:
            print(f"⚠️ Error getting schema for {collection_name}: {e}")
            return {"fields": [], "typed_fields": [], "sample": [], "count": 0}
    
    def _preload_schemas(self):
        """Preload schema for all collections to speed up query generation"""
        print(f"🧠 Preloading schemas for {len(self.collections)} collections...")
        for coll in self.collections:
            # We call the real method with use_cache=False to avoid infinite loop
            # and then populate it
            self.schema_cache[coll] = self._get_collection_schema(coll, use_cache=False)
        print("✅ All schemas preloaded and cached.")
    
    def _infer_collection(self, query: str) -> Optional[str]:
        """Infer collection name from query"""
        query_lower = query.lower()
        # 0. Check for meta/conversational/general keywords - avoid forcing a collection
        meta_keywords = [
            "permission", "help", "who are you", "what can you", "hi", "hello", 
            "thank", "access", "policy", "role", "system", "status", "info", 
            "capabilities", "tutorial", "guide", "explain"
        ]
        
        # Use regex to match only whole words to prevent false positives (e.g. 'shipped' containing 'hi')
        for kw in meta_keywords:
            if re.search(rf"\b{re.escape(kw)}\b", query_lower):
                print(f"🕵️ Detected meta-keyword '{kw}' in query. Avoiding collection default.")
                return None
        
        query_clean = query_lower.replace(" ", "")

        # 1. Direct match or within query (handling spaces)
        for collection in self.collections:
            coll_lower = collection.lower()
            # Exact match
            if coll_lower in query_lower:
                return collection
            # Match without spaces (e.g., "categorie s" -> "categories")
            if coll_lower in query_clean:
                return collection
            # Match singular version (e.g., "product" -> "products")
            if coll_lower.endswith('s') and coll_lower[:-1] in query_clean:
                return collection
            # Match plural version (e.g., "categories" -> "category" - complex but helps)
            if not coll_lower.endswith('s') and coll_lower + 's' in query_clean:
                return collection
        
        # 2. Match common collections as fallback
        common_collections = ["products", "orders", "customers", "categories", "users", "movies"]
        for common in common_collections:
            if common in self.collections:
                # Still check if common name is in query
                if common in query_clean or (common.endswith('s') and common[:-1] in query_clean):
                    return common
        
        # 3. Only default if we are fairly sure it's a data question, or return None to let LLM decide
        # Removing the "force products" default to prevent hallucinations on meta-questions
        return None
    
    def _build_query_prompt(self, natural_query: str, collection: Optional[str] = None, history: Optional[List[Dict[str, str]]] = None, permissions: Optional[Dict[str, Any]] = None, user_role: Optional[str] = None, policy_name: Optional[str] = None, template_override: Optional[str] = None) -> str:
        """Build prompt for LLM to generate MongoDB query"""
        
        # Infer collection if not provided
        if not collection:
            collection = self._infer_collection(natural_query)
        
        # Format permissions context
        permission_text = ""
        is_denied = False
        
        if permissions:
            active_db = self.db.name if self.db is not None else None
            collections_policy = permissions.get('collections', [])
            max_limit = permissions.get('maxLimit', 100)
            
            # Find matching policy
            coll_policy = None
            
            # Priority 1: Exact Database + Exact Collection
            if active_db:
                coll_policy = next((c for c in collections_policy if c.get('database') == active_db and c['name'] == collection), None)
            
            # Priority 2: Exact Database + Wildcard Collection
            if not coll_policy and active_db:
                coll_policy = next((c for c in collections_policy if c.get('database') == active_db and c['name'] == '*'), None)
            
            # Priority 3: Wildcard Database + Exact Collection
            if not coll_policy:
                coll_policy = next((c for c in collections_policy if (c.get('database', '*') == '*') and c['name'] == collection), None)
            
            # Priority 4: Wildcard Database + Wildcard Collection
            if not coll_policy:
                coll_policy = next((c for c in collections_policy if (c.get('database', '*') == '*') and c['name'] == '*'), None)

            permission_text = "\nDATA GOVERNANCE POLICIES (MANDATORY):\n"
            if coll_policy:
                allowed_ops = ", ".join(coll_policy.get('operations', ['find']))
                restricted_fields = ", ".join(coll_policy.get('restrictedFields', []))
                
                permission_text += f"- User Role: {user_role or 'Unknown'}\n"
                permission_text += f"- Policy Name: {policy_name or 'Default'}\n"
                permission_text += f"- Allowed operations: {allowed_ops}\n"
                permission_text += f"- Maximum result limit allowed: {max_limit}\n"
                if restricted_fields:
                    permission_text += f"- RESTRICTED FIELDS (STRICTLY PROHIBITED): {restricted_fields}\n"
                
                permission_text += "- You ARE authorized to perform the operations listed above. If the user asks for these, proceed with generating the MQL.\n"
                
                # Metadata / Schema permissions for admins
                if user_role and user_role.lower() in ['admin', 'manager', 'superuser']:
                    permission_text += "- You HAVE ADMINISTRATIVE PRIVILEGES. You are authorized to describe the database schema, list collections, and explain the structure of the data.\n"
                
                permission_text += "- If the user asks for a restricted field, explain why you cannot provide it and offer a safe alternative.\n"
            else:
                is_denied = True
                if collection:
                    permission_text += f"ACCESS DENIED: You are NOT allowed to access the '{collection}' collection in database '{active_db}'.\n"
                    permission_text += "- Explain to the user that they do not have permissions for this data and suggest what they ARE allowed to access.\n"
                else:
                    permission_text += f"METADATA ACCESS: You are querying the database structure of '{active_db}'.\n"
                    if user_role and user_role.lower() in ['admin', 'manager', 'superuser']:
                        permission_text += "- You are an ADMIN. You are authorized to explain the schema and available data.\n"
                    else:
                        permission_text += "- You have limited access. Only discuss general database capabilities.\n"
        else:
            max_limit = 100 # Default if no permissions provided

        # Refresh collection names for context
        self.collections = self.db.list_collection_names()
        
        # Get schema information (only if not denied)
        schema_info = {}
        if collection and not is_denied:
            schema_info = self._get_collection_schema(collection)
        
        # Format history if available
        history_text = ""
        if history:
            history_text = "\nPREVIOUS CONVERSATION CONTEXT:\n"
            for msg in history[-5:]: # Last 5 messages for context
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")
                history_text += f"{role}: {content}\n"
        
        default_template = """You are an elite MongoDB Data Engineer and AI Assistant. Your job is to translate natural language questions into precise, executable MongoDB queries.

=== PHASE 1: SILENT REASONING (Think before generating) ===
Before writing any JSON, reason through these steps internally:
1. INTENT: Is this conversational, a visualization request, or a data query?
2. TARGET: Which collection(s) does this query involve?
3. FILTERS: What conditions must be applied? What field types are involved?
4. JOINS: Are cross-collection lookups needed? What are the join keys?
5. AGGREGATION: Does this need grouping, counting, or summing?
6. VALIDATE: Do all field names exist in the schema? Do operators match field types?

=== INPUT CONTEXT ===
Database: {database_name}
Permissions: {permission_text}
Conversation History: {history_text}

=== DATABASE SCHEMA (GROUND TRUTH - USE ONLY THESE FIELDS) ===
{collections_structure}

=== ⚠️ CRITICAL FIELD NAME MAPPING (EXACT NAMES FROM SCHEMA - DO NOT INVENT) ===

**orders collection EXACT FIELD NAMES:**
- ✅ CORRECT: "user"           ❌ NEVER: "userId", "user_id", "customerId"
- ✅ CORRECT: "total_amount"   ❌ NEVER: "total", "amount", "totalAmount"
- ✅ CORRECT: "order_date"     ❌ NEVER: "createdAt", "date", "orderDate"
- ✅ CORRECT: "items"          ← array of {product, quantity, price, _id}
- ✅ CORRECT: "items.product"  ❌ NEVER: "items.product_id", "items.productId", "productId"
  ⛔ The $lookup localField for joining products is ALWAYS "items.product" — NOT "items.product_id", "items.productId"  
  ⛔ Example: { "$lookup": { "from": "products", "localField": "items.product", "foreignField": "_id", "as": "product_info" } }
- ❌ NEVER: "items.product_name", "items.name", "items.title"  ← THESE FIELDS DO NOT EXIST
  → To get product name you MUST use aggregate + $lookup to join products collection
- ✅ CORRECT: "status"         (values: 'pending', 'shipped', 'delivered', 'cancelled')

**products collection EXACT FIELD NAMES:**
- ✅ CORRECT: "_id"            ← join target from items.product
- ✅ CORRECT: "name"           ← product name
- ✅ CORRECT: "price"
- ✅ CORRECT: "category"       (ObjectId → categories._id)
- ❌ NEVER: "productId", "product_id", "id"

**customers collection EXACT FIELD NAMES:**
- ✅ CORRECT: "_id", "first_name", "last_name", "email"
- ❌ NEVER: "name" (customers have first_name + last_name, NOT name)

**users collection EXACT FIELD NAMES:**
- ✅ CORRECT: "_id", "name", "email", "role"  (only 1 admin user — NOT for orders)

=== KNOWN RELATIONSHIPS (CRITICAL FOR JOINS) ===
- orders.user → customers._id     ✅ (NOT users._id — users collection has only 1 admin)
- orders.items[].product → products._id  ✅ (NOT items.product_id, NOT items.productId)
- products.category → categories._id    ✅

⛔ orders does NOT have any of these fields: customer, customer_name, customer.name, username, name
   The only link to a customer is orders.user (an ObjectId). The customer's name lives in the customers collection.
   → To filter/show customer info in orders, you MUST use $lookup to join customers on orders.user = customers._id
   → To search orders by customer name: $lookup(customers) → $unwind → $match on customer_info.first_name / last_name
   → NEVER use operation:"find" with query:{"customer.name":...} or {"username":...} on orders — those fields do not exist.

=== NATURAL LANGUAGE → MQL OPERATOR MAPPING ===
| Natural Language          | MQL Operator                          |
|---------------------------|---------------------------------------|
| equals / is               | { field: value }                      |
| not equal / is not        | { field: { $ne: value } }             |
| greater than / more than  | { field: { $gt: value } }             |
| less than / under         | { field: { $lt: value } }             |
| at least / >= / min       | { field: { $gte: value } }            |
| at most / <= / max        | { field: { $lte: value } }            |
| between X and Y (dates)   | { field: { $gte: X, $lte: Y } }       |
| contains / like           | { field: { $regex: "pat", $options: "i" } } |
| starts with               | { field: { $regex: "^pat", $options: "i" } } |
| in list / one of          | { field: { $in: [v1, v2] } }          |
| not in list               | { field: { $nin: [v1, v2] } }         |
| top N / highest N         | sort descending + limit N             |
| bottom N / lowest N       | sort ascending + limit N              |
| count / how many          | $count or $group with $sum: 1         |
| total / sum of            | $group with $sum: "$field"            |
| average / mean            | $group with $avg: "$field"            |
| group by / per            | $group with _id: "$field"             |

=== ARRAY FIELD HANDLING (arrays are like sub-tables) ===

**WRONG APPROACH:**
- DON'T try: "products.productId" - this field doesn't exist in products!
- DON'T assume field names without checking schema first
- DON'T apply $limit AFTER $unwind when you want to limit ORDERS (not rows)

**CORRECT APPROACH FOR arrays:**
1. When an order has items[], each item has: {product (ObjectId), quantity, price}
2. Use "localField": "items.product", "foreignField": "_id" to join products
3. Apply $sort + $limit BEFORE $unwind to get N orders (not N rows)
4. ALWAYS $group AFTER $unwind to consolidate products per order

**PERFORMANCE RULE:** $sort → $limit → $unwind → $lookup → $group (this order matters!)

**CORRECT Example C: Orders for a customer by name**
Query: "List out the orders of the customer named Art"
{
  "type": "database",
  "explanation": "orders.user is an ObjectId — cannot filter by name directly. Must $lookup customers first, then $match on name.",
  "mql": {
    "collection": "orders",
    "operation": "aggregate",
    "pipeline": [
      { "$lookup": { "from": "customers", "localField": "user", "foreignField": "_id", "as": "customer_info" } },
      { "$unwind": { "path": "$customer_info", "preserveNullAndEmptyArrays": false } },
      { "$match": { "$or": [ { "customer_info.first_name": { "$regex": "Art", "$options": "i" } }, { "customer_info.last_name": { "$regex": "Art", "$options": "i" } } ] } },
      { "$project": { "order_date": 1, "total_amount": 1, "status": 1, "customer_name": { "$concat": ["$customer_info.first_name", " ", "$customer_info.last_name"] } } },
      { "$limit": 20 }
    ]
  }
}

**⛔ MANDATORY RULE: After $unwind(items) + $lookup(products), you MUST use $group to produce ONE document per order.**
- NEVER end the pipeline with $project after $unwind — that gives 1 row per product, not 1 row per order.
- ALWAYS group by "$_id" and use $addToSet to collect product names into an array.
- Even if the user only asks for product names (not username), the $group stage is REQUIRED.

**CORRECT Example A: Last 5 orders — product names only (no username requested)**
Query: "List out the last 5 orders product name"
{
  "type": "database",
  "explanation": "Sort and limit to 5 orders first, unwind items, lookup products, then GROUP to get one row per order with all product names.",
  "mql": {
    "collection": "orders",
    "operation": "aggregate",
    "pipeline": [
      { "$sort": { "order_date": -1 } },
      { "$limit": 5 },
      { "$unwind": { "path": "$items" } },
      { "$lookup": { "from": "products", "localField": "items.product", "foreignField": "_id", "as": "product_info" } },
      { "$unwind": { "path": "$product_info", "preserveNullAndEmptyArrays": true } },
      { "$group": { "_id": "$_id", "order_date": { "$first": "$order_date" }, "total_amount": { "$first": "$total_amount" }, "status": { "$first": "$status" }, "product_names": { "$addToSet": "$product_info.name" } } },
      { "$sort": { "order_date": -1 } }
    ]
  }
}

**CORRECT Example B: Last 5 orders with username and product names**
Query: "Last 5 orders with product names and username"
{
  "type": "database",
  "explanation": "Sort and limit FIRST to 5 orders, then unwind items, lookup products and customers, group back by order.",
  "mql": {
    "collection": "orders",
    "operation": "aggregate",
    "pipeline": [
      { "$sort": { "order_date": -1 } },
      { "$limit": 5 },
      { "$lookup": { "from": "customers", "localField": "user", "foreignField": "_id", "as": "customer_info" } },
      { "$unwind": { "path": "$customer_info", "preserveNullAndEmptyArrays": true } },
      { "$unwind": { "path": "$items" } },
      { "$lookup": { "from": "products", "localField": "items.product", "foreignField": "_id", "as": "product_info" } },
      { "$unwind": { "path": "$product_info", "preserveNullAndEmptyArrays": true } },
      { "$group": { "_id": "$_id", "order_date": { "$first": "$order_date" }, "username": { "$first": { "$concat": ["$customer_info.first_name", " ", "$customer_info.last_name"] } }, "product_names": { "$addToSet": "$product_info.name" }, "total_amount": { "$first": "$total_amount" } } },
      { "$sort": { "order_date": -1 } }
    ]
  }
}

QUERY RULES (MANDATORY) ===
1. **SCHEMA ADHERENCE (MANDATORY):** ONLY use fields listed in the schema below. Check field names character-by-character:
   - ❌ WRONG: "userId", "user_id", "userId" → ✅ CORRECT: "user"
   - ❌ WRONG: "total", "amount", "order_amount" → ✅ CORRECT: "total_amount"
   - ❌ WRONG: "createdAt", "created_date", "date" → ✅ CORRECT: "order_date"
   - ❌ WRONG: "products.productId" → ✅ CORRECT: "items.product" (and join to products._id)
   - ❌ WRONG: "items.product_name", "items.name" → THESE FIELDS DO NOT EXIST. Must use $lookup.
   - If a field is not in the schema, YOU CANNOT use it. Never invent fields.
1b. **FIND vs AGGREGATE:** Use `operation: "find"` ONLY when all needed fields are DIRECTLY on the collection.
   - If the query requires product names, customer names, or ANY field from another collection → use `operation: "aggregate"` with $lookup.
   - If the query accesses items[] array and needs product info → ALWAYS use `operation: "aggregate"`.
   - NEVER use `find` with `projection: {"items.product_name": 1}` — that field does not exist.
   - NEVER use dot-notation projection on ObjectId reference fields (e.g., `items.product` is an ObjectId, not an object with name).
2. **ARRAY HANDLING:** When collection has nested arrays (e.g., orders.items):
   - ALWAYS check field names inside the array first (see schema: items has {product, quantity, price})
   - The $lookup localField to join products is ALWAYS "items.product" — NEVER "items.product_id", "items.productId"
   - MANDATORY pipeline order: $sort → $limit → $unwind($items) → $lookup(products) → $unwind(product_info) → $group
   - Apply $sort + $limit BEFORE $unwind when limiting N orders (not N rows)
   - ⛔ NEVER end with $project after $unwind — you will get 1 row per product, ruining the results
   - ✅ ALWAYS end with $group (group by "$_id") to consolidate back to 1 document per order
   - In $group use $addToSet: "$product_info.name" to collect all product names into an array
   - Use $unwind with "preserveNullAndEmptyArrays": true to keep orders with no products
   - After $group, fields like product_names are arrays (rendered as chips in UI)
3. **NAME SEARCH (searching orders/products by a person's name):**
   - Customer names live in the `customers` collection, NOT in `orders`.
   - To find orders by customer name: use `aggregate` with `$lookup(customers)` → `$unwind` → `$match` on `first_name`/`last_name`.
   - NEVER use `find` on `orders` with `customer.name`, `customer_name`, or `username` — those fields do not exist in orders.
   - For name matching always use `$regex` on BOTH `first_name` AND `last_name` with `$or` and `$options: "i"`.
4. **DATE FIELDS:** Use ISO 8601 format: ISODate("YYYY-MM-DDT00:00:00Z")
5. **TEXT SEARCH:** Always use $regex with $options: "i" for case-insensitive matching.
6. **JOINS ($lookup):**
   a. Apply $match on the BASE collection BEFORE $lookup when possible.
   b. If filtering joined collection, put $match INSIDE $lookup.pipeline.
   c. Use $unwind only when flattening arrays for further processing.
   d. Use correct join keys from schema (orders.user→customers._id, NOT orders.userId)
7. **SAFETY:** NEVER generate deleteOne, updateOne, drop, or any write operation.
8. **LIMITS:** Default limit is 20 for find, unless user specifies otherwise.
9. **NO SQL:** Never use SELECT, JOIN, WHERE. Only MongoDB operators.
10. **VALIDATION BEFORE RETURNING:** Check $lookup keys exist. Check all field names are in schema.

=== OUTPUT CONTRACT ===
Return ONLY a single valid JSON object. No markdown, no explanation outside JSON, no trailing commas.

Validation checklist (verify before responding):
- [ ] All field names exist in the schema above
- [ ] Operators match the field type (e.g., $regex only on strings, $gt only on numbers/dates)
- [ ] Aggregation stage order is valid: $sort → $limit → $lookup → $unwind → $group (for array queries)
- [ ] Used `aggregate` (NOT `find`) when any field from another collection is needed
- [ ] No dot-notation projection on ObjectId array reference fields (items.product, etc.)
- [ ] Output is valid, parseable JSON
- [ ] No write operations included

=== RESPONSE FORMATS ===

**CATEGORY 1 — CONVERSATIONAL** (greetings, identity questions, listing tables, general MongoDB questions, questions impossible to answer from schema)
{
  "type": "conversational",
  "response": "Your helpful response in Markdown. If asked about available data, list collections from the schema."
}

**CATEGORY 2 — VISUALIZATION** (chart, graph, plot, trend, distribution, compare)
{
  "type": "visualization",
  "chart_type": "bar" | "line" | "pie" | "doughnut",
  "title": "Descriptive Chart Title",
  "x_key": "label",
  "y_key": "value",
  "explanation": "Brief explanation.",
  "mql": {
    "collection": "collection_name",
    "operation": "aggregate",
    "pipeline": [
      { "$group": { "_id": "$field", "value": { "$sum": 1 } } },
      { "$project": { "_id": 0, "label": "$_id", "value": 1 } },
      { "$sort": { "value": -1 } }
    ]
  }
}

**CATEGORY 3 — DATABASE** (find, search, show, list, get, count, filter)
{
  "type": "database",
  "explanation": "Brief explanation of the query logic.",
  "mql": {
    "collection": "collection_name",
    "operation": "find" | "aggregate",
    "query": { ... },
    "pipeline": [ ... ],
    "projection": { ... },
    "sort": { ... },
    "limit": 20
  }
}

=== FEW-SHOT EXAMPLES ===

**Example 1 — Simple Find**
Query: "Find users who have admin role"
{
  "type": "database",
  "explanation": "Filtering users collection where role equals admin.",
  "mql": { "collection": "users", "operation": "find", "query": { "role": "admin" }, "projection": { "name": 1, "email": 1, "role": 1 }, "limit": 20 }
}

**Example 2 — Name Search (BOTH first_name and last_name)**
Query: "Show orders for customer named Jackeline"
{
  "type": "database",
  "explanation": "Joining orders with customers and filtering by first_name using regex.",
  "mql": {
    "collection": "orders",
    "operation": "aggregate",
    "pipeline": [
      { "$lookup": { "from": "customers", "localField": "user", "foreignField": "_id", "as": "customer" } },
      { "$unwind": "$customer" },
      { "$match": { "$or": [ { "customer.first_name": { "$regex": "Jackeline", "$options": "i" } }, { "customer.last_name": { "$regex": "Jackeline", "$options": "i" } } ] } },
      { "$project": { "_id": 1, "total_amount": 1, "status": 1, "order_date": 1, "customer_name": { "$concat": ["$customer.first_name", " ", "$customer.last_name"] } } }
    ],
    "limit": 20
  }
}

**Example 3 — Date Range**
Query: "Show orders placed in December 2025"
{
  "type": "database",
  "explanation": "Filtering orders where order_date falls within December 2025.",
  "mql": {
    "collection": "orders",
    "operation": "find",
    "query": { "order_date": { "$gte": { "$date": "2025-12-01T00:00:00Z" }, "$lte": { "$date": "2025-12-31T23:59:59Z" } } },
    "sort": { "order_date": -1 },
    "limit": 20
  }
}

**Example 4 — Aggregation (Revenue by Status)**
Query: "Show total revenue grouped by order status"
{
  "type": "database",
  "explanation": "Grouping orders by status and summing total_amount.",
  "mql": {
    "collection": "orders",
    "operation": "aggregate",
    "pipeline": [
      { "$group": { "_id": "$status", "total_revenue": { "$sum": "$total_amount" }, "count": { "$sum": 1 } } },
      { "$sort": { "total_revenue": -1 } }
    ]
  }
}

**Example 5 — Top-N**
Query: "Show top 5 most expensive products"
{
  "type": "database",
  "explanation": "Sorting products by price descending and limiting to 5.",
  "mql": { "collection": "products", "operation": "find", "query": {}, "sort": { "price": -1 }, "limit": 5 }
}

**Example 5b — Top customers by spending (CRITICAL: group by _id, use $ifNull for names)**
Query: "Top 50 customers who have spent the most, showing name, email, total amount spent, and number of orders"
{
  "type": "database",
  "explanation": "Joining orders with customers, grouping by customer _id so each customer appears once. $ifNull prevents null names. Revenue comes from summing total_amount per customer.",
  "mql": {
    "collection": "orders",
    "operation": "aggregate",
    "pipeline": [
      { "$lookup": { "from": "customers", "localField": "user", "foreignField": "_id", "as": "customer_info" } },
      { "$unwind": { "path": "$customer_info", "preserveNullAndEmptyArrays": false } },
      {
        "$group": {
          "_id": "$customer_info._id",
          "customerName": { "$first": { "$concat": [{ "$ifNull": ["$customer_info.first_name", ""] }, " ", { "$ifNull": ["$customer_info.last_name", ""] }] } },
          "customerEmail": { "$first": { "$ifNull": ["$customer_info.email", ""] } },
          "totalAmountSpent": { "$sum": "$total_amount" },
          "numberOfOrders": { "$sum": 1 }
        }
      },
      { "$sort": { "totalAmountSpent": -1 } },
      { "$limit": 50 },
      { "$project": { "_id": 0, "customerName": 1, "customerEmail": 1, "totalAmountSpent": 1, "numberOfOrders": 1 } }
    ]
  }
}

**Example 5c — Embedded array aggregation (products stored as items[] with quantity)**
Query: "What is the total delivered product count and total revenue from delivered orders?"
{
  "type": "database",
  "explanation": "Filtering to delivered orders only, then unwinding the embedded items array to access each product's quantity. Summing quantity gives total units sold; summing total_amount (once per order before unwind) gives revenue.",
  "mql": {
    "collection": "orders",
    "operation": "aggregate",
    "pipeline": [
      { "$match": { "status": "delivered" } },
      { "$unwind": "$items" },
      {
        "$group": {
          "_id": null,
          "totalProductCount": { "$sum": "$items.quantity" },
          "totalRevenue": { "$sum": "$total_amount" }
        }
      },
      {
        "$project": {
          "_id": 0,
          "totalProductCount": 1,
          "totalRevenue": { "$round": ["$totalRevenue", 2] }
        }
      }
    ]
  }
}
⚠️ NOTE: When summing total_amount per-order (not per-item), do NOT unwind before the $group — or group by order _id first, then sum. Here we use total_amount directly inside $group after unwind because total_amount belongs to the order document (not the items subdocument), so $sum: "$total_amount" will multiply-count. The CORRECT pattern for revenue across delivered orders is:
- STEP 1 $match status=delivered
- STEP 2 $group by _id (order), totalRevenue: $sum $total_amount (BEFORE unwind to avoid double-counting)
- STEP 3 $unwind items  — or use separate $project after group

For this specific case (delivered orders revenue + item quantity), use the pipeline above which counts items.quantity correctly and reads total_amount from the order-level field (no double-count since $sum:"$total_amount" sums the same value for each unwound item — this IS a double-count risk). The SAFE version is:

{
  "collection": "orders",
  "operation": "aggregate",
  "pipeline": [
    { "$match": { "status": "delivered" } },
    {
      "$facet": {
        "revenue": [
          { "$group": { "_id": null, "totalRevenue": { "$sum": "$total_amount" } } }
        ],
        "products": [
          { "$unwind": "$items" },
          { "$group": { "_id": null, "totalProductCount": { "$sum": "$items.quantity" } } }
        ]
      }
    },
    {
      "$project": {
        "totalRevenue": { "$round": [{ "$arrayElemAt": ["$revenue.totalRevenue", 0] }, 2] },
        "totalProductCount": { "$arrayElemAt": ["$products.totalProductCount", 0] }
      }
    }
  ]
}

**Example 6 — Visualization**
Query: "Show a bar chart of product counts by category"
{
  "type": "visualization",
  "chart_type": "bar",
  "title": "Product Count by Category",
  "x_key": "label",
  "y_key": "value",
  "explanation": "Grouping products by category and counting.",
  "mql": {
    "collection": "products",
    "operation": "aggregate",
    "pipeline": [
      { "$group": { "_id": "$category", "value": { "$sum": 1 } } },
      { "$project": { "_id": 0, "label": "$_id", "value": 1 } },
      { "$sort": { "value": -1 } }
    ]
  }
}

**Example 7 — Conversational**
Query: "What tables are available?"
{
  "type": "conversational",
  "response": "Here are the available collections in **{database_name}**:\n\n- **orders** - Customer orders\n- **customers** - Customer profiles\n- **products** - Product catalog\n- **categories** - Product categories\n\nYou can ask me to query any of these!"
}

=== NEGATIVE EXAMPLES (NEVER DO THIS) ===
❌ Using $regex on a numeric field: { "total_amount": { "$regex": "100" } } — WRONG. Use { "total_amount": { "$gt": 100 } }
❌ Inventing fields not in schema: { "customerName": "Jackeline" } — WRONG if schema has first_name/last_name
❌ SQL syntax: SELECT * FROM orders WHERE status = 'shipped' — WRONG. Use MongoDB find/aggregate
❌ Unwinding without lookup: { "$unwind": "$user" } when user is an ObjectId — WRONG. Join first with $lookup
❌ Mixed projection (1 and 0 together): { "name": 1, "email": 0 } — WRONG. Use only inclusions or only exclusions (except _id)
❌ Filtering joined data AFTER unwind when it could be pushed into $lookup.pipeline — INEFFICIENT

=== SCHEMA MATCHING STRATEGY ===
If the exact field name is not in the schema:
1. Look for a field with similar meaning (e.g., user asked for "customer name" → use first_name + last_name)
2. Look for nested fields using dot notation (e.g., "city" → "address.city")
3. NEVER invent a field that does not exist in the schema
4. If truly ambiguous, explain in the "explanation" field what assumption you made

---
USER QUERY: {natural_query}

RESPONSE (JSON ONLY):"""

        template = template_override if template_override else default_template
        
        # Ensure the query placeholder exists in the template if it's an override
        if template_override and "{natural_query}" not in template_override:
            print("⚠️ Warning: Custom prompt template missing '{natural_query}' placeholder. Appending it automatically.")
            template += "\n\n--- \nUSER QUERY: {natural_query}\n\nRESPONSE (JSON ONLY):"
        
        # Prepare collections structure with typed schema - IMPROVED FORMAT
        collections_structure = "All available collections, their fields, types, and sample values:\n\n"
        for coll_name in self.collections:
            coll_schema = self._get_collection_schema(coll_name)
            typed_fields = coll_schema.get('typed_fields', [])
            if typed_fields:
                field_lines = []
                for f in typed_fields:
                    field_type = f['type']
                    sub_fields = f.get('sub_fields', [])
                    
                    # Mark arrays clearly and show sub-fields
                    if field_type == 'array<object>' and sub_fields:
                        sub_str = ', '.join(sub_fields)
                        type_str = f"array<object> → each item has: {{{sub_str}}}"
                        field_lines.append(f"  • {f['field']} 🔗 {type_str}")
                    elif field_type.startswith('array'):
                        samples = f['sample_values']
                        sample_str = f", e.g.: {' / '.join(str(s)[:40] for s in samples[:2])}" if samples else ""
                        field_lines.append(f"  • {f['field']} 🔗 {field_type}{sample_str}")
                    else:
                        type_str = f"({field_type})"
                        samples = f['sample_values']
                        sample_str = ""
                        if samples:
                            sample_str = f", e.g.: {' / '.join(str(s)[:40] for s in samples[:2])}"
                        field_lines.append(f"  • {f['field']} {type_str}{sample_str}")
                
                field_desc = "\n".join(field_lines)
                collections_structure += f"📋 **{coll_name.upper()}** [{coll_schema.get('count', 0)} docs]\n{field_desc}\n\n"
            else:
                fields = coll_schema.get('fields', [])
                collections_structure += f"📋 **{coll_name.upper()}**: [{', '.join(fields)}]\n\n"
            
        if collection:
            collections_structure += f"\n⭐ PRIMARY FOCUS: The user's query likely focuses on the '{collection}' collection."
        
        # Performance replacements
        replacements = {
            "{permission_text}": permission_text,
            "{history_text}": history_text,
            "{database_name}": self.database_name,
            "{collections_structure}": collections_structure,
            "{collections_list}": ", ".join(self.collections), # Support custom prompt key
            "{current_collection}": collection if collection else "Not specified", # Support custom prompt key
            "{fields_list}": ", ".join(schema_info.get("fields", [])) if schema_info else "Unknown", # Support custom prompt key
            "{natural_query}": natural_query,
            "{max_limit}": str(max_limit)
        }
        
        final_prompt = template
        for key, value in replacements.items():
            final_prompt = final_prompt.replace(key, value)
        
        # Final fallback - if for some reason natural_query still isn't in there (e.g. key was wrong)
        if natural_query not in final_prompt:
            final_prompt += f"\n\nUSER QUERY: {natural_query}\nRESPONSE (JSON ONLY):"
            
        print(f"DEBUG: Using prompt source: {'Database Override' if template_override else 'System Default'}")
        
        return final_prompt
    
    def _extract_mql_from_response(self, response: Any) -> Dict[str, Any]:
        """Extract MongoDB query from LLM response"""
        try:
            content = ""
            if isinstance(response, list):
                # Handle cases where response is a list of content blocks
                for block in response:
                    if isinstance(block, dict) and "text" in block:
                        content += block["text"]
                    elif isinstance(block, str):
                        content += block
            else:
                content = str(response)

            # 1. Try to find JSON in markdown code blocks first
            json_blocks = []
            code_blocks = re.findall(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
            for block in code_blocks:
                try:
                    # Clean up the block (Sometimes LLMs put text outside the JSON)
                    clean_block_match = re.search(r'\{.*\}', block, re.DOTALL)
                    if clean_block_match:
                        json_blocks.append(json.loads(clean_block_match.group()))
                except:
                    continue
            
            # 2. If no valid JSON in code blocks, search the whole content
            if not json_blocks:
                # Find all potential JSON objects using a balanced brace approach (simplified)
                # or just iterative searches
                matches = re.finditer(r'\{', content)
                for match in matches:
                    start_idx = match.start()
                    # Try to find the matching closing brace
                    stack = 0
                    for i in range(start_idx, len(content)):
                        if content[i] == '{':
                            stack += 1
                        elif content[i] == '}':
                            stack -= 1
                            if stack == 0:
                                json_candidate = content[start_idx:i+1]
                                try:
                                    # Basic cleanup: remove common problematic characters
                                    # but try standard parse first
                                    json_blocks.append(json.loads(json_candidate))
                                except:
                                    # Try a more aggressive cleanup for broken JSON
                                    try:
                                        # Remove trailing commas
                                        cleaned = re.sub(r',\s*([\]}])', r'\1', json_candidate)
                                        json_blocks.append(json.loads(cleaned))
                                    except:
                                        pass
                                break
            
            # 3. Choose the most relevant result
            if json_blocks:
                # Filter for ones that have 'type'
                valid_blocks = [b for b in json_blocks if isinstance(b, dict) and 'type' in b]
                if valid_blocks:
                    # Priority: visualization > database > conversational
                    priority = {"visualization": 3, "database": 2, "conversational": 1}
                    valid_blocks.sort(key=lambda x: priority.get(x.get('type', ''), 0), reverse=True)
                    return valid_blocks[0]
                return json_blocks[0]
            
            # FALLBACK: If no JSON was found, assume the LLM responded in plain text (common for refuses or failures)
            print(f"⚠️ No JSON blocks found. Falling back to conversational response.")
            return {
                "type": "conversational",
                "response": content.strip() or "I'm sorry, I couldn't process that request properly. Could you try rephrasing it?"
            }
        except Exception as e:
            print(f"⚠️ Error in _extract_mql_from_response: {e}")
            return {
                "type": "conversational",
                "response": f"I encountered an error while processing your request: {str(e)}"
            }
    
    def _convert_dates(self, obj: Any) -> Any:
        """Recursively convert { '$date': '...' } Extended JSON to Python datetime objects"""
        from datetime import datetime, timezone
        if isinstance(obj, dict):
            if "$date" in obj and len(obj) == 1:
                date_str = obj["$date"]
                try:
                    # Handle ISO 8601 with Z suffix
                    if date_str.endswith('Z'):
                        date_str = date_str[:-1] + '+00:00'
                    return datetime.fromisoformat(date_str)
                except Exception:
                    return obj
            return {k: self._convert_dates(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_dates(item) for item in obj]
        return obj

    def _execute_query(self, mql: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute MongoDB query"""
        try:
            # Fix common LLM structure issues
            mql = self._fix_mql(mql)
            
            collection_name = mql.get("collection")
            operation = mql.get("operation", "find")
            
            if not collection_name:
                raise ValueError("Collection name not specified in query")
            
            collection = self.db[collection_name]
            
            if operation == "aggregate":
                pipeline = mql.get("pipeline", [])
                pipeline = self._convert_dates(pipeline)  # Convert $date Extended JSON
                results = list(collection.aggregate(pipeline))
            elif operation == "delete":
                query_filter = mql.get("query", {})
                if not query_filter:
                    raise ValueError("Delete operations must have a filter for safety")
                
                # For "first 5", we might need to find IDs first since deleteMany doesn't support limit/sort directly
                sort = mql.get("sort")
                limit = mql.get("limit")
                
                if limit or sort:
                    # Find the specific IDs to delete
                    cursor = collection.find(query_filter, {"_id": 1})
                    if sort:
                        if isinstance(sort, dict):
                            cursor = cursor.sort(list(sort.items()))
                        else:
                            cursor = cursor.sort(sort)
                    if limit:
                        cursor = cursor.limit(limit)
                    
                    ids_to_delete = [doc["_id"] for doc in cursor]
                    result = collection.delete_many({"_id": {"$in": ids_to_delete}})
                else:
                    result = collection.delete_many(query_filter)
                    
                return [{"success": True, "deleted_count": result.deleted_count}]
            else:
                # Standard find operation
                query_filter = mql.get("query", {})
                query_filter = self._convert_dates(query_filter)  # Convert $date Extended JSON
                projection = mql.get("projection")
                sort = mql.get("sort")
                limit = mql.get("limit", 1000) # Increased default to 100
                
                cursor = collection.find(query_filter, projection)
                
                if sort:
                    if isinstance(sort, dict):
                        cursor = cursor.sort(list(sort.items()))
                    else:
                        cursor = cursor.sort(sort)
                
                cursor = cursor.limit(min(limit, 100000)) # Increased cap to 1000 for 'all' requests
                results = list(cursor)
            
            # Convert ObjectId and datetime to string for JSON serialization
            def stringify_ids(data):
                if isinstance(data, list):
                    return [stringify_ids(item) for item in data]
                if isinstance(data, dict):
                    return {k: stringify_ids(v) for k, v in data.items()}
                from bson import ObjectId
                from datetime import datetime
                if isinstance(data, ObjectId):
                    return str(data)
                if isinstance(data, datetime):
                    return data.isoformat()
                return data

            return stringify_ids(results)
        
        except Exception as e:
            print(f"❌ Error executing query: {e}")
            raise

    def _validate_mql_against_permissions(self, mql: Dict[str, Any], permissions: Dict[str, Any], active_db: Optional[str] = None) -> tuple[bool, str]:
        """Validate MQL components against user permissions"""
        if not permissions:
            return True, ""
            
        collections_policy = permissions.get('collections', [])
        max_limit = permissions.get('maxLimit', 100)
        target_collection = mql.get('collection')
        
        # 1. Find matching policy
        policy = None
        
        # Priority 1: Exact Database + Exact Collection
        if active_db:
            policy = next((c for c in collections_policy if c.get('database') == active_db and c['name'] == target_collection), None)
            
        # Priority 2: Exact Database + Wildcard Collection
        if not policy and active_db:
            policy = next((c for c in collections_policy if c.get('database') == active_db and c['name'] == '*'), None)
            
        # Priority 3: Wildcard Database + Exact Collection
        if not policy:
            policy = next((c for c in collections_policy if (c.get('database', '*') == '*') and c['name'] == target_collection), None)
            
        # Priority 4: Wildcard Database + Wildcard Collection
        if not policy:
            policy = next((c for c in collections_policy if (c.get('database', '*') == '*') and c['name'] == '*'), None)
            
        if not policy:
            return False, f"Access to collection '{target_collection}' in database '{active_db}' is not allowed."
            
        # 2. Validate Operation
        op = mql.get('operation', 'find').lower()
        allowed_ops = policy.get('operations', ['find'])
        if op not in allowed_ops:
            return False, f"Operation '{op}' is not allowed on collection '{target_collection}'. Allowed: {', '.join(allowed_ops)}"
            
        # 3. Validate Limit
        limit = mql.get('limit')
        if limit and limit > max_limit:
            return False, f"Requested limit {limit} exceeds the maximum allowed limit of {max_limit}."

        # 4. Validate Restricted Fields
        restricted_fields = policy.get('restrictedFields', [])
        if restricted_fields:
            # Check query filter
            query_str = json.dumps(mql.get('query', {}))
            for field in restricted_fields:
                if f'"{field}"' in query_str:
                    return False, f"Accessing restricted field '{field}' in query filter is prohibited."
            
            # Check projection
            projection = mql.get('projection', {})
            for field in restricted_fields:
                if projection.get(field):
                    return False, f"Accessing restricted field '{field}' in projection is prohibited."
                    
            # Check aggregation pipeline
            if op == 'aggregate':
                pipeline_str = json.dumps(mql.get('pipeline', []))
                for field in restricted_fields:
                    if f'"{field}"' in pipeline_str:
                        return False, f"Accessing restricted field '{field}' in aggregation pipeline is prohibited."
                        
        return True, ""

    def generate_query_plan(self, natural_query: str, collection: Optional[str] = None, history: Optional[List[Dict[str, str]]] = None, permissions: Optional[Dict[str, Any]] = None, user_role: Optional[str] = None, policy_name: Optional[str] = None, custom_system_prompt: Optional[str] = None, visualization_hint: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a query plan (MQL + Explanation) without executing it.
        If visualization_hint is provided with enabled=True, we generate guaranteed-correct MQL.
        """
        start_time = time.time()
        try:
            print(f"\n📝 Generating query plan for: {natural_query}")
            
            # LLM-based logic will handle "list tables" using the schema context provided.
            # No need for hardcoded pattern matching here.
            
            # Extract debug mode preference
            debug_mode = visualization_hint.get('debugMode', 'auto') if visualization_hint else 'auto'
            print(f"🔧 Debug Mode: {debug_mode}")
            
            # Determine whether to use smart templates or LLM
            use_smart_template = False
            
            if debug_mode == 'template':
                use_smart_template = True
                print("🔧 DEBUG: Forcing smart template generation")
            elif debug_mode == 'llm':
                use_smart_template = False
                print("🔧 DEBUG: Forcing LLM generation (User selected 'LLM')")
            elif debug_mode == 'auto' or debug_mode is None:
                # DEFAULT: Always use LLM for the most "real" and flexible experience.
                # Only use templates if the user specifically asked for them via 'debug_mode=template'.
                use_smart_template = False
                print("🎯 Auto mode: Delegating to LLM for full analysis on real data")
            
            # NEW: Generate smart MQL if conditions are met
            if use_smart_template:
                # Determine chart type
                if visualization_hint and visualization_hint.get('chartType'):
                    chart_type = visualization_hint.get('chartType', 'bar')
                else:
                    # Force template mode without explicit chart type - default to bar
                    chart_type = 'bar'
                
                print(f"📋 Generating {chart_type} chart using smart template")
                
                mql = self._build_visualization_mql(natural_query, chart_type, collection)
                
                return {
                    "success": True,
                    "mql_query": mql,
                    "explanation": f"I've prepared a {chart_type} chart for your query using a reliable template. This ensures correct data labels and fast response.",
                    "type": "visualization",
                    "chart_type": chart_type,
                    "title": self._extract_title(natural_query),
                    "x_key": "label",
                    "y_key": "value",
                    "needs_confirmation": True,
                    "metadata": {
                        "provider": "smart_mql",
                        "model": "hardcoded",
                        "debug_mode": debug_mode,
                        "type": "visualization",
                        "total_time": time.time() - start_time
                    }
                }
            
            # LLM-based logic below (when use_smart_template is False)
            print("🤖 Using LLM to generate query plan")
            # 1. Local NLP Analysis
            print("🔍 Step 1: Local NLP Analysis...")
            local_analysis = processor.analyze_query(natural_query) if processor else {}
            
            # 2. Build prompt
            print("📝 Step 2: Building prompt...")
            # We use the custom_system_prompt as a template override if it exists
            prompt = self._build_query_prompt(natural_query, collection, history, permissions, user_role, policy_name, template_override=custom_system_prompt)
            
            # 3. Get response from LLM
            print(f"🤖 Step 3: Invoking LLM ({self.llm_metadata['provider']} / {self.llm_metadata['model']})...")
            
            # If we have a custom prompt, we've already used it to build the main instruction set (the human prompt)
            # So the system message can be a simpler baseline.
            system_instruction = f"You are a helpful and intelligent MongoDB AI Assistant. Your mission is to truly understand the user's request and provide the most helpful response possible. While you MUST provide your final answer in a strict raw JSON format (no markdown blocks), you should use the 'explanation' and 'response' fields to speak naturally to the user, acknowledging their intent and providing clear, context-aware information. User role: {user_role or 'Analyst'}."
            
            print("\n" + "🚀" + "="*48)
            print(f"📝 USER QUERY: {natural_query}")
            if custom_system_prompt:
                print(f"📜 CUSTOM INSTRUCTIONS: {custom_system_prompt[:200]}..." if len(custom_system_prompt) > 200 else f"📜 CUSTOM INSTRUCTIONS: {custom_system_prompt}")
            else:
                print("📜 INSTRUCTIONS: Using system default")
            print("="*50 + "\n")

            messages = [
                SystemMessage(content=system_instruction),
                HumanMessage(content=prompt)
            ]
            
            # ========== DETAILED PROMPT LOGGING ==========
            print("\n" + "="*80)
            print("📤 FULL PROMPT BEING SENT TO LLM")
            print("="*80)
            print(f"\n🔧 LLM Provider: {self.llm_metadata['provider']}")
            print(f"🤖 LLM Model: {self.llm_metadata['model']}")
            print(f"\n📋 SYSTEM MESSAGE:")
            print("-" * 80)
            print(system_instruction)
            print("-" * 80)
            print(f"\n💬 HUMAN MESSAGE (Prompt):")
            print("-" * 80)
            print(prompt)
            print("-" * 80)
            print(f"\n📊 Total Messages: {len(messages)}")
            print(f"📏 System Message Length: {len(system_instruction)} characters")
            print(f"📏 Human Message Length: {len(prompt)} characters")
            print(f"📏 Total Prompt Length: {len(system_instruction) + len(prompt)} characters")
            print("="*80 + "\n")
            # ============================================
            
            llm_start_time = time.time()
            print(f"⏰ Sending request to {self.llm_metadata['provider']} at {time.strftime('%H:%M:%S')}...")
            response = self.llm.invoke(messages)
            print(f"⏱️ LLM response received in {time.time() - llm_start_time:.2f}s")
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Extract LLM output
            print("🧪 Step 4: Extracting MQL...")
            print(f"DEBUG: Raw LLM Output:\n{response_text}\n" + "-"*50)
            llm_output = self._extract_mql_from_response(response_text)
            
            if not llm_output:
                raise ValueError("Failed to process request")
            
            # Handle conversational response or null MQL (fallback to conversational)
            is_conversational = llm_output.get("type") == "conversational"
            has_mql = llm_output.get("mql") is not None
            
            if is_conversational or not has_mql:
                print(f"💬 Response is {'conversational' if is_conversational else 'denied/unanswerable'}.")
                response_msg = llm_output.get("response") or llm_output.get("explanation") or "I'm here to help you query your MongoDB database. How can I assist you today?"
                
                return {
                    "success": True,
                    "mql_query": None,
                    "explanation": response_msg,
                    "needs_confirmation": False,
                    "metadata": {
                        "provider": self.llm_metadata["provider"],
                        "model": self.llm_metadata["model"],
                        "type": "conversational",
                        "total_time": time.time() - start_time
                    }
                }
            
            # Handle visualization
            if llm_output.get("type") == "visualization":
                print(f"📊 Response is a visualization ({llm_output.get('chart_type', 'bar')}).")
                mql = llm_output.get("mql", {})
                
                # Ensure collection is set
                if not mql.get("collection") and collection:
                    mql["collection"] = collection
                elif not mql.get("collection"):
                    mql["collection"] = self._infer_collection(natural_query)
                    
                mql = self._fix_mql(mql)
                
                return {
                    "success": True,
                    "mql_query": mql,
                    "explanation": llm_output.get("explanation", f"I have prepared a {llm_output.get('chart_type', 'chart')} for your request."),
                    "type": "visualization",
                    "chart_type": llm_output.get("chart_type", "bar"),
                    "title": llm_output.get("title", "Data Visualization"),
                    "x_key": llm_output.get("x_key", "label"),
                    "y_key": llm_output.get("y_key", "value"),
                    "needs_confirmation": True,
                    "metadata": {
                        "provider": self.llm_metadata["provider"],
                        "model": self.llm_metadata["model"],
                        "type": "visualization",
                        "total_time": time.time() - start_time
                    }
                }

            # Handle database query
            print("💾 Response is a database query.")
            mql = llm_output.get("mql", llm_output) # Fallback if LLM didn't wrap it
            
            # Ensure collection is set (fallback to inferred if LLM omits it)
            if not mql.get("collection") and collection:
                mql["collection"] = collection
            elif not mql.get("collection"):
                mql["collection"] = self._infer_collection(natural_query)
                
            mql = self._fix_mql(mql) # Fix common LLM mistakes
            
            # Validate against permissions
            if permissions:
                print("🛡️ Step 5: Validating against permissions...")
                is_allowed, reason = self._validate_mql_against_permissions(mql, permissions, active_db=self.db.name if self.db is not None else None)
                if not is_allowed:
                    print(f"⚠️ Security violation: {reason}")
                    return {
                        "success": False,
                        "mql_query": None,
                        "explanation": f"⚠️ SECURITY POLICY VIOLATION: {reason}\nYou are not authorized to perform this operation or access these fields.",
                        "needs_confirmation": False,
                        "error": "PolicyViolation",
                        "metadata": {
                            "provider": self.llm_metadata["provider"],
                            "model": self.llm_metadata["model"],
                            "violation": True,
                            "total_time": time.time() - start_time
                        }
                    }
            
            # Validate safety
            print("🛡️ Step 6: Validating MQL safety...")
            is_safe, error_msg = validate_mql_safety(mql)
            if not is_safe:
                print(f"⚠️ Safety violation: {error_msg}")
                return {
                    "success": False,
                    "mql_query": mql,
                    "explanation": f"⚠️ Query safety violation: {error_msg}",
                    "needs_confirmation": False,
                    "error": "SafetyViolation",
                    "metadata": {
                        "provider": self.llm_metadata["provider"],
                        "model": self.llm_metadata["model"],
                        "total_time": time.time() - start_time
                    }
                }
            
            # 4. Success for standard DB query
            print("✅ Query plan generated successfully.")
            return {
                "success": True,
                "mql_query": mql,
                "explanation": llm_output.get("explanation", "I have generated a MongoDB query for your request."),
                "needs_confirmation": True,
                "metadata": {
                    "provider": self.llm_metadata["provider"],
                    "model": self.llm_metadata["model"],
                    "total_time": time.time() - start_time
                }
            }
        except Exception as e:
            print(f"❌ Error generating plan: {e}")
            return {
                "success": False,
                "mql_query": None,
                "explanation": f"Error generating query plan: {str(e)}",
                "needs_confirmation": False,
                "error": str(e),
                "metadata": {
                    "provider": self.llm_metadata["provider"],
                    "model": self.llm_metadata["model"],
                    "total_time": time.time() - start_time
                }
            }

    def execute_mql(self, mql: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a previously generated and confirmed MQL query"""
        try:
            results = self._execute_query(mql)
            return {
                "success": True,
                "results": results,
                "metadata": {
                    "provider": self.llm_metadata["provider"],
                    "model": self.llm_metadata["model"],
                    "result_count": len(results)
                }
            }
        except Exception as e:
            print(f"❌ Error executing confirmed query: {e}")
            raise

    def process_query(self, natural_query: str, collection: Optional[str] = None, history: Optional[List[Dict[str, str]]] = None, permissions: Optional[Dict[str, Any]] = None, user_role: Optional[str] = None, policy_name: Optional[str] = None, custom_system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Process natural language query and return results.
        
        Args:
            natural_query: Natural language query string
            collection: Optional collection name
            history: Optional chat history
            permissions: Optional role permissions
            user_role: Optional user role name
            policy_name: Optional role policy name
        
        Returns:
            Dictionary with results, MQL, and metadata
        """
        try:
            # For backward compatibility, generate plan and then execute
            plan = self.generate_query_plan(natural_query, collection, history, permissions, user_role, policy_name, custom_system_prompt)
            if not plan["success"]:
                return plan
            
            # If conversational, return directly
            if not plan["mql_query"]:
                return {
                    "success": True,
                    "mql_query": None,
                    "results": [],
                    "collection": None,
                    "explanation": plan["explanation"],
                    "metadata": plan["metadata"]
                }
            
            execution = self.execute_mql(plan["mql_query"])
            
            # Prepare base response
            response = {
                "success": True,
                "mql_query": plan["mql_query"],
                "results": execution["results"],
                "collection": plan["mql_query"].get("collection"),
                "explanation": plan.get("explanation", f"Found {len(execution['results'])} results."),
                "metadata": execution["metadata"]
            }

            # Add visualization metadata if present
            for key in ["type", "chart_type", "title", "x_key", "y_key"]:
                if key in plan:
                    response[key] = plan[key]

            return response
        
        except Exception as e:
            print(f"❌ Error processing query: {e}")
            return {
                "success": False,
                "error": str(e),
                "mql_query": None,
                "results": [],
                "explanation": f"Error: {str(e)}",
                "metadata": {
                    "provider": self.llm_metadata["provider"],
                    "model": self.llm_metadata["model"]
                }
            }

    
    def _build_visualization_mql(self, query: str, chart_type: str, collection_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Build guaranteed-correct visualization MQL with $lookup for ObjectId references.
        This bypasses the LLM to ensure correct chart rendering.
        """
        query_lower = query.lower()
        
        # Infer collection if not provided
        collection = collection_hint
        if not collection:
            if 'product' in query_lower:
                collection = 'products'
            elif 'order' in query_lower:
                collection = 'orders'
            elif 'customer' in query_lower:
                collection = 'customers'
            elif 'category' in query_lower or 'categories' in query_lower:
                collection = 'categories'
            else:
                collection = 'products'  # Default
        
        # Define common visualization patterns with $lookup
        # These handle ObjectId references correctly
        if collection == 'products' and ('category' in query_lower or 'categories' in query_lower):
            # Products grouped by category NAME (not ID)
            return {
                "collection": "products",
                "operation": "aggregate",
                "pipeline": [
                    {
                        "$lookup": {
                            "from": "categories",
                            "localField": "category",
                            "foreignField": "_id",
                            "as": "category_info"
                        }
                    },
                    { "$unwind": { "path": "$category_info", "preserveNullAndEmptyArrays": True } },
                    { "$group": { "_id": "$category_info.name", "value": { "$sum": 1 } } },
                    { "$project": { "_id": 0, "label": "$_id", "value": 1 } },
                    { "$sort": { "value": -1 } },
                    { "$limit": 10 }
                ]
            }
        
        elif collection == 'orders' and 'customer' in query_lower:
            # Orders grouped by customer name
            return {
                "collection": "orders",
                "operation": "aggregate",
                "pipeline": [
                    {
                        "$lookup": {
                            "from": "customers",
                            "localField": "user",
                            "foreignField": "_id",
                            "as": "customer_info"
                        }
                    },
                    { "$unwind": { "path": "$customer_info", "preserveNullAndEmptyArrays": True } },
                    { 
                        "$group": { 
                            "_id": { 
                                "$concat": ["$customer_info.first_name", " ", "$customer_info.last_name"]
                            }, 
                            "value": { "$sum": 1  } 
                        } 
                    },
                    { "$project": { "_id": 0, "label": "$_id", "value": 1 } },
                    { "$sort": { "value": -1 } },
                    { "$limit": 10 }
                ]
            }
        
        elif collection == 'categories':
            # Categories by product count
            return {
                "collection": "categories",
                "operation": "aggregate",
                "pipeline": [
                    {
                        "$lookup": {
                            "from": "products",
                            "localField": "_id",
                            "foreignField": "category",
                            "as": "products"
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "label": "$name",
                            "value": { "$size": "$products" }
                        }
                    },
                    { "$sort": { "value": -1 } },
                    { "$limit": 10 }
                ]
            }
        
        else:
            # Generic: Group by a field (fallback)
            # Try to find the most likely grouping field
            group_by = "$name" if 'name' in query_lower else "$status" if 'status' in query_lower else "$_id"
            
            return {
                "collection": collection,
                "operation": "aggregate",
                "pipeline": [
                    { "$group": { "_id": group_by, "value": { "$sum": 1 } } },
                    { "$project": { "_id": 0, "label": "$_id", "value": 1 } },
                    { "$sort": { "value": -1 } },
                    { "$limit": 10 }
                ]
            }

    def _extract_title(self, query: str) -> str:
        """Extract a nice title from the user's query."""
        # Simple title extraction
        query = query.strip().capitalize()
        if len(query) > 50:
            return query[:47] + "..."
        return query
    
    def close(self):
        """Close MongoDB connection"""
        self.client.close()
        print("🔌 MongoDB connection closed")
