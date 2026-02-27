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
        self.connection_string = connection_string
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

    def set_database(self, database_name: str):
        """Switch active database context for subsequent prompt/schema/query operations."""
        if not database_name or database_name == self.database_name:
            return

        print(f"🔄 Switching database context: {self.database_name} -> {database_name}")
        self.db = self.client[database_name]
        self.database_name = database_name
        self.collections = self.db.list_collection_names()
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

        # 3. Normalize common field-name aliases to real schema names
        mql = self._normalize_field_aliases(mql)
        mql = self._normalize_common_join_mistakes(mql)
        
        return mql

    def _normalize_common_join_mistakes(self, mql: Dict[str, Any]) -> Dict[str, Any]:
        """Fix frequent cross-collection join mistakes in aggregate pipelines."""
        if not isinstance(mql, dict):
            return mql
        if mql.get("collection") != "orders" or mql.get("operation") != "aggregate":
            return mql

        pipeline = mql.get("pipeline")
        if not isinstance(pipeline, list):
            return mql

        def replace_paths(obj: Any, old_prefix: str, new_prefix: str) -> Any:
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    new_k = k
                    if isinstance(k, str) and k.startswith(old_prefix):
                        new_k = new_prefix + k[len(old_prefix):]
                    out[new_k] = replace_paths(v, old_prefix, new_prefix)
                return out
            if isinstance(obj, list):
                return [replace_paths(i, old_prefix, new_prefix) for i in obj]
            if isinstance(obj, str):
                if obj.startswith(f"${old_prefix}"):
                    return f"${new_prefix}{obj[len(old_prefix)+1:]}"
                return obj
            return obj

        normalized = pipeline
        renamed_user_info = False

        for i, stage in enumerate(normalized):
            if not isinstance(stage, dict):
                continue
            lookup = stage.get("$lookup")
            if not isinstance(lookup, dict):
                continue

            local_field = lookup.get("localField")
            from_coll = lookup.get("from")
            foreign_field = lookup.get("foreignField")
            as_field = lookup.get("as")

            # orders.user always points to customers._id in this schema.
            if local_field == "user" and from_coll == "users":
                lookup["from"] = "customers"
                if foreign_field != "_id":
                    lookup["foreignField"] = "_id"
                if as_field == "user_info":
                    lookup["as"] = "customer_info"
                    renamed_user_info = True

            # Common product join path mistakes.
            if from_coll == "products" and isinstance(local_field, str):
                if local_field in {"items.product_id", "items.productId"}:
                    lookup["localField"] = "items.product"

            normalized[i]["$lookup"] = lookup

        if renamed_user_info:
            normalized = replace_paths(normalized, "user_info", "customer_info")

            # If matching by customer_info.name, expand to first_name/last_name match.
            for idx, stage in enumerate(normalized):
                if not isinstance(stage, dict) or "$match" not in stage:
                    continue
                match_obj = stage.get("$match", {})
                if not isinstance(match_obj, dict):
                    continue
                if "customer_info.name" in match_obj:
                    name_expr = match_obj.pop("customer_info.name")
                    normalized[idx]["$match"] = {
                        "$and": [
                            match_obj,
                            {
                                "$or": [
                                    {"customer_info.first_name": name_expr},
                                    {"customer_info.last_name": name_expr},
                                    {
                                        "$expr": {
                                            "$regexMatch": {
                                                "input": {
                                                    "$concat": [
                                                        {"$ifNull": ["$customer_info.first_name", ""]},
                                                        " ",
                                                        {"$ifNull": ["$customer_info.last_name", ""]}
                                                    ]
                                                },
                                                "regex": name_expr.get("$regex", "") if isinstance(name_expr, dict) else str(name_expr),
                                                "options": name_expr.get("$options", "i") if isinstance(name_expr, dict) else "i"
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }

        mql["pipeline"] = normalized
        return mql

    def _normalize_field_aliases(self, mql: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize common field aliases used by LLMs to actual schema field names."""
        if not isinstance(mql, dict):
            return mql

        collection = mql.get("collection")
        if not collection:
            return mql

        alias_map_by_collection = {
            "orders": {
                "total": "total_amount",
                "amount": "total_amount",
                "totalAmount": "total_amount",
                "orderDate": "order_date",
                "createdAt": "order_date",
                "date": "order_date",
                "userId": "user",
                "user_id": "user",
                "customerId": "user",
                "product_id": "product",
                "productId": "product"
            },
            "products": {
                "productId": "_id",
                "product_id": "_id",
                "category_id": "category",
                "categoryId": "category",
                "stock_quantity": "stock",
                "stockQty": "stock",
                "inventory": "stock",
                "inventory_count": "stock"
            },
            "customers": {
                "name": "first_name"
            }
        }

        alias_map = alias_map_by_collection.get(collection, {})
        if not alias_map:
            return mql

        def normalize_path(path: str) -> str:
            if not isinstance(path, str):
                return path
            if path.startswith("$"):
                sigil = "$"
                raw = path[1:]
            else:
                sigil = ""
                raw = path

            parts = raw.split(".")
            normalized = [alias_map.get(p, p) for p in parts]
            return f"{sigil}{'.'.join(normalized)}"

        def normalize_dict_keys(obj: Any) -> Any:
            operator_arg_keys = {
                "date", "format", "timezone", "onNull",
                "unit", "binSize", "startOfWeek"
            }
            if isinstance(obj, dict):
                out = {}
                for key, value in obj.items():
                    if isinstance(key, str) and key.startswith("$"):
                        # Normalize argument keys for date operators:
                        # $dateToString/$dateTrunc must use "date", not field-name keys.
                        if key in {"$dateToString", "$dateTrunc"} and isinstance(value, dict):
                            fixed = dict(value)
                            if "date" not in fixed:
                                for wrong_key in ["order_date", "created_at", "createdAt", "field"]:
                                    if wrong_key in fixed:
                                        fixed["date"] = fixed.pop(wrong_key)
                                        break
                            out[key] = normalize_dict_keys(fixed)
                        else:
                            out[key] = normalize_dict_keys(value)
                    else:
                        # Do not rewrite MongoDB operator argument keys (e.g. $dateToString.date)
                        if isinstance(key, str) and key in operator_arg_keys:
                            new_key = key
                        else:
                            new_key = normalize_path(key) if isinstance(key, str) else key
                        # localField/foreignField are field-path values (not "$" expressions)
                        if isinstance(key, str) and key in {"localField", "foreignField"} and isinstance(value, str):
                            out[new_key] = normalize_path(value)
                        else:
                            out[new_key] = normalize_dict_keys(value)
                return out
            if isinstance(obj, list):
                return [normalize_dict_keys(i) for i in obj]
            if isinstance(obj, str) and obj.startswith("$"):
                return normalize_path(obj)
            return obj

        for section in ["query", "projection", "sort"]:
            if section in mql and isinstance(mql[section], dict):
                mql[section] = normalize_dict_keys(mql[section])

        if "pipeline" in mql and isinstance(mql["pipeline"], list):
            mql["pipeline"] = normalize_dict_keys(mql["pipeline"])

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
        """Recursively convert date-like payloads to Python datetime objects."""
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
        elif isinstance(obj, str):
            # Convert plain ISO date strings as well (LLM often returns these in filters).
            try:
                # Guard to avoid converting arbitrary strings.
                if len(obj) >= 10 and (obj[4:5] == "-" or obj.endswith("Z")):
                    date_str = obj
                    if date_str.endswith("Z"):
                        date_str = date_str[:-1] + "+00:00"
                    return datetime.fromisoformat(date_str)
            except Exception:
                return obj
        return obj

    def _convert_objectids(self, obj: Any, key_path: str = "") -> Any:
        """Recursively convert ObjectId-like strings for id/reference fields."""
        if isinstance(obj, dict):
            converted = {}
            for k, v in obj.items():
                next_path = f"{key_path}.{k}" if key_path else str(k)
                converted[k] = self._convert_objectids(v, next_path)
            return converted

        if isinstance(obj, list):
            return [self._convert_objectids(item, key_path) for item in obj]

        if isinstance(obj, str) and ObjectId.is_valid(obj):
            # Convert only for likely id/reference field paths, not arbitrary strings.
            leaf = key_path.split(".")[-1] if key_path else ""
            normalized_path = key_path.lower()
            id_leafs = {
                "_id", "id", "user", "customer", "product", "category",
                "userid", "customerid", "productid", "categoryid"
            }
            if (
                leaf.lower() in id_leafs
                or leaf.lower().endswith("_id")
                or any(p in normalized_path for p in [".user", ".product", ".category", "items.product"])
                or any(op in normalized_path for op in ["$in", "$nin", "$eq"])
            ):
                try:
                    return ObjectId(obj)
                except Exception:
                    return obj

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
                pipeline = self._convert_objectids(pipeline)
                results = list(collection.aggregate(pipeline))
            elif operation == "delete":
                query_filter = mql.get("query", {})
                query_filter = self._convert_objectids(query_filter)
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
                query_filter = self._convert_objectids(query_filter)
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
            
            # Resolve common references in orders for better readability in UI tables.
            if collection_name == "orders":
                results = self._enrich_order_results(results)

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

    def _enrich_order_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Resolve customer/product ObjectIds in orders to readable names."""
        if not results:
            return results

        try:
            customer_ids = set()
            product_ids = set()

            for doc in results:
                if not isinstance(doc, dict):
                    continue

                user_val = doc.get("user")
                if isinstance(user_val, ObjectId):
                    customer_ids.add(user_val)

                items = doc.get("items")
                if not isinstance(items, list):
                    continue

                for item in items:
                    if isinstance(item, dict):
                        p = item.get("product")
                        if isinstance(p, ObjectId):
                            product_ids.add(p)
                    elif isinstance(item, ObjectId):
                        product_ids.add(item)

            customer_map = {}
            if customer_ids:
                for c in self.db["customers"].find(
                    {"_id": {"$in": list(customer_ids)}},
                    {"first_name": 1, "last_name": 1}
                ):
                    full_name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
                    customer_map[c["_id"]] = full_name or str(c["_id"])

            product_map = {}
            if product_ids:
                for p in self.db["products"].find(
                    {"_id": {"$in": list(product_ids)}},
                    {"name": 1}
                ):
                    product_map[p["_id"]] = p.get("name") or str(p["_id"])

            enriched_docs = []
            for doc in results:
                if not isinstance(doc, dict):
                    enriched_docs.append(doc)
                    continue

                new_doc = dict(doc)

                user_val = new_doc.get("user")
                if isinstance(user_val, ObjectId) and user_val in customer_map:
                    new_doc["user_name"] = customer_map[user_val]

                items = new_doc.get("items")
                if isinstance(items, list):
                    item_names = []
                    new_items = []
                    for item in items:
                        if isinstance(item, dict):
                            item_doc = dict(item)
                            p = item_doc.get("product")
                            if isinstance(p, ObjectId) and p in product_map:
                                item_doc["product_name"] = product_map[p]
                                item_names.append(product_map[p])
                            new_items.append(item_doc)
                        elif isinstance(item, ObjectId):
                            pname = product_map.get(item, str(item))
                            new_items.append({"product": item, "product_name": pname})
                            item_names.append(pname)
                        else:
                            new_items.append(item)

                    new_doc["items"] = new_items
                    if item_names:
                        new_doc["item_names"] = list(dict.fromkeys(item_names))

                enriched_docs.append(new_doc)

            return enriched_docs
        except Exception as e:
            print(f"Warning: order enrichment skipped: {e}")
            return results

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

    def _validate_mql_against_schema(self, mql: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate generated MQL fields against real collection schema.
        Strict check is applied for `find` operations.
        """
        if not isinstance(mql, dict):
            return False, "MQL must be an object."

        collection_name = mql.get("collection")
        operation = str(mql.get("operation", "find")).lower()

        if not collection_name:
            return False, "Collection name not specified in query."
        if collection_name not in self.collections:
            return False, f"Collection '{collection_name}' does not exist in database '{self.db.name}'."

        schema = self._get_collection_schema(collection_name)
        allowed_fields = set(schema.get("fields", []))
        if not allowed_fields:
            return True, ""

        def iter_user_fields(obj: Any):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(key, str):
                        if not key.startswith("$"):
                            yield key
                        yield from iter_user_fields(value)
            elif isinstance(obj, list):
                for item in obj:
                    yield from iter_user_fields(item)

        invalid_fields = set()
        for section in ("query", "projection", "sort"):
            section_obj = mql.get(section, {})
            if not isinstance(section_obj, dict):
                continue
            for field in iter_user_fields(section_obj):
                if not field:
                    continue
                root = field.split(".")[0]
                if root not in allowed_fields:
                    invalid_fields.add(field)

        if invalid_fields:
            invalid = ", ".join(sorted(invalid_fields))
            allowed = ", ".join(sorted(allowed_fields))
            return False, f"Invalid field(s): {invalid}. Allowed root fields: {allowed}."

        if operation == "aggregate":
            pipeline = mql.get("pipeline", [])
            if not isinstance(pipeline, list):
                return False, "Aggregation pipeline must be an array."

            derived_roots = set()
            allowed_roots = set(allowed_fields)

            def root_from_ref(ref: str) -> Optional[str]:
                if not isinstance(ref, str) or not ref.startswith("$") or ref.startswith("$$"):
                    return None
                path = ref[1:]
                if not path:
                    return None
                return path.split(".")[0]

            def collect_ref_roots(obj: Any) -> set[str]:
                roots = set()
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str):
                            root = root_from_ref(v)
                            if root:
                                roots.add(root)
                        roots |= collect_ref_roots(v)
                elif isinstance(obj, list):
                    for item in obj:
                        roots |= collect_ref_roots(item)
                elif isinstance(obj, str):
                    root = root_from_ref(obj)
                    if root:
                        roots.add(root)
                return roots

            for stage in pipeline:
                if not isinstance(stage, dict):
                    continue

                if "$lookup" in stage and isinstance(stage["$lookup"], dict):
                    lookup = stage["$lookup"]
                    local_field = lookup.get("localField")
                    if isinstance(local_field, str):
                        local_root = local_field.split(".")[0]
                        if local_root not in allowed_roots and local_root not in derived_roots:
                            return False, f"Invalid $lookup localField '{local_field}' for collection '{collection_name}'."

                    as_field = lookup.get("as")
                    if isinstance(as_field, str) and as_field:
                        derived_roots.add(as_field.split(".")[0])

                if "$facet" in stage and isinstance(stage["$facet"], dict):
                    for facet_key, facet_pipeline in stage["$facet"].items():
                        if isinstance(facet_key, str) and facet_key:
                            derived_roots.add(facet_key.split(".")[0])
                        for root in collect_ref_roots(facet_pipeline):
                            if root not in allowed_roots and root not in derived_roots and root != "_id":
                                return False, f"Invalid field reference '${root}' in $facet pipeline."

                if "$unwind" in stage:
                    unwind = stage["$unwind"]
                    unwind_path = unwind.get("path") if isinstance(unwind, dict) else unwind
                    if isinstance(unwind_path, str) and unwind_path.startswith("$"):
                        unwind_root = unwind_path[1:].split(".")[0]
                        if unwind_root not in allowed_roots and unwind_root not in derived_roots:
                            return False, f"Invalid $unwind path '{unwind_path}' for collection '{collection_name}'."

                if "$group" in stage and isinstance(stage["$group"], dict):
                    for out_key in stage["$group"].keys():
                        if out_key != "_id":
                            derived_roots.add(out_key.split(".")[0])

                if "$addFields" in stage and isinstance(stage["$addFields"], dict):
                    for out_key in stage["$addFields"].keys():
                        derived_roots.add(out_key.split(".")[0])

                for root in collect_ref_roots(stage):
                    if root not in allowed_roots and root not in derived_roots and root != "_id":
                        return False, f"Invalid field reference '${root}' for collection '{collection_name}'."

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
            
            # Schema-first deterministic fallback for common business intents.
            # This avoids LLM hallucinations on known query patterns.
            rule_based_mql = self._build_rule_based_mql(natural_query, collection)
            if rule_based_mql:
                return {
                    "success": True,
                    "mql_query": rule_based_mql,
                    "explanation": "I generated this query using a schema-verified deterministic template for accuracy.",
                    "needs_confirmation": True,
                    "metadata": {
                        "provider": "rule_based",
                        "model": "schema_first",
                        "type": "database",
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
                x_key = llm_output.get("x_key", "label")
                y_key = llm_output.get("y_key", "value")
                if isinstance(x_key, list):
                    x_key = x_key[0] if x_key else "label"
                if isinstance(y_key, list):
                    y_key = y_key[0] if y_key else "value"
                if not isinstance(x_key, str):
                    x_key = str(x_key)
                if not isinstance(y_key, str):
                    y_key = str(y_key)
                
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
                    "x_key": x_key,
                    "y_key": y_key,
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

            # Validate schema correctness for generated query
            is_schema_valid, schema_reason = self._validate_mql_against_schema(mql)
            if not is_schema_valid:
                print(f"Schema validation failed on first attempt: {schema_reason}")
                print("Retrying once with schema feedback...")

                repair_instruction = (
                    f"{prompt}\n\n"
                    "=== SCHEMA VALIDATION FEEDBACK (MUST FIX) ===\n"
                    f"Previous MQL failed validation: {schema_reason}\n"
                    "Regenerate using only valid schema fields and return JSON only."
                )
                repair_messages = [
                    SystemMessage(content=system_instruction),
                    HumanMessage(content=repair_instruction)
                ]
                repair_response = self.llm.invoke(repair_messages)
                repair_text = repair_response.content if hasattr(repair_response, 'content') else str(repair_response)
                print(f"DEBUG: Repair LLM Output:\n{repair_text}\n" + "-" * 50)
                repaired_output = self._extract_mql_from_response(repair_text)

                if repaired_output and repaired_output.get("mql") is not None:
                    repaired_mql = repaired_output.get("mql", repaired_output)
                    if not repaired_mql.get("collection") and collection:
                        repaired_mql["collection"] = collection
                    elif not repaired_mql.get("collection"):
                        repaired_mql["collection"] = self._infer_collection(natural_query)
                    repaired_mql = self._fix_mql(repaired_mql)

                    repaired_ok, repaired_reason = self._validate_mql_against_schema(repaired_mql)
                    if repaired_ok:
                        mql = repaired_mql
                        llm_output = repaired_output
                        is_schema_valid = True
                        print("Schema-repair retry succeeded.")
                    else:
                        schema_reason = repaired_reason
                        print(f"Schema-repair retry failed: {schema_reason}")
            if not is_schema_valid:
                return {
                    "success": False,
                    "mql_query": mql,
                    "explanation": f"⚠️ Query schema validation failed: {schema_reason}",
                    "needs_confirmation": False,
                    "error": "SchemaValidationFailed",
                    "metadata": {
                        "provider": self.llm_metadata["provider"],
                        "model": self.llm_metadata["model"],
                        "total_time": time.time() - start_time
                    }
                }
            
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

    def execute_mql(self, mql: Dict[str, Any], permissions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a previously generated and confirmed MQL query"""
        try:
            if not isinstance(mql, dict):
                raise ValueError("Invalid MQL payload")

            mql = self._fix_mql(mql)

            # Re-validate confirmed MQL before execution to prevent tampering/replay abuse.
            is_safe, error_msg = validate_mql_safety(mql)
            if not is_safe:
                raise ValueError(f"Query safety violation: {error_msg}")

            is_schema_valid, schema_reason = self._validate_mql_against_schema(mql)
            if not is_schema_valid:
                raise ValueError(f"Query schema validation failed: {schema_reason}")

            if permissions:
                is_allowed, reason = self._validate_mql_against_permissions(
                    mql,
                    permissions,
                    active_db=self.db.name if self.db is not None else None
                )
                if not is_allowed:
                    raise ValueError(f"Security policy violation: {reason}")

            results = self._execute_query(mql)
            return {
                "success": True,
                "results": results,
                "metadata": {
                    "provider": self.llm_metadata["provider"],
                    "model": self.llm_metadata["model"],
                    "result_count": len(results),
                    "validated_at_execute": True
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

    
    def _build_rule_based_mql(self, natural_query: str, collection_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return deterministic schema-safe MQL for known intents, else None."""
        q = (natural_query or "").lower()
        complex_markers = [
            "return both",
            "executive analytics",
            "top 15 customers",
            "ranked table",
            "top_3_product_names",
            "strict schema adherence",
            "line-chart-ready monthly trend",
            "also include one separate mql"
        ]
        is_complex_request = any(marker in q for marker in complex_markers)

        # Intent: orders of customer named X with item names and customer name.
        if (not is_complex_request) and ("order" in q) and ("named" in q) and ("item" in q):
            name_match = re.search(r"named\s+([a-zA-Z][a-zA-Z\s\-]{1,60})", natural_query, re.IGNORECASE)
            person_name = name_match.group(1).strip() if name_match else ""
            person_name = re.split(r"\b(with|and|show|list|get)\b", person_name, flags=re.IGNORECASE)[0].strip()
            if person_name:
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
                        {"$unwind": {"path": "$customer_info", "preserveNullAndEmptyArrays": False}},
                        {
                            "$match": {
                                "$expr": {
                                    "$regexMatch": {
                                        "input": {
                                            "$trim": {
                                                "input": {
                                                    "$concat": [
                                                        {"$ifNull": ["$customer_info.first_name", ""]},
                                                        " ",
                                                        {"$ifNull": ["$customer_info.last_name", ""]}
                                                    ]
                                                }
                                            }
                                        },
                                        "regex": re.escape(person_name),
                                        "options": "i"
                                    }
                                }
                            }
                        },
                        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": True}},
                        {
                            "$lookup": {
                                "from": "products",
                                "localField": "items.product",
                                "foreignField": "_id",
                                "as": "product_info"
                            }
                        },
                        {"$unwind": {"path": "$product_info", "preserveNullAndEmptyArrays": True}},
                        {
                            "$group": {
                                "_id": "$_id",
                                "customer_name": {
                                    "$first": {
                                        "$trim": {
                                            "input": {
                                                "$concat": [
                                                    {"$ifNull": ["$customer_info.first_name", ""]},
                                                    " ",
                                                    {"$ifNull": ["$customer_info.last_name", ""]}
                                                ]
                                            }
                                        }
                                    }
                                },
                                "item_names": {"$addToSet": "$product_info.name"},
                                "status": {"$first": "$status"},
                                "total_amount": {"$first": "$total_amount"},
                                "order_date": {"$first": "$order_date"}
                            }
                        },
                        {
                            "$project": {
                                "_id": 0,
                                "order_id": "$_id",
                                "customer_name": 1,
                                "item_names": {
                                    "$filter": {
                                        "input": "$item_names",
                                        "as": "n",
                                        "cond": {"$ne": ["$$n", None]}
                                    }
                                },
                                "status": 1,
                                "total_amount": 1,
                                "order_date": 1
                            }
                        },
                        {"$sort": {"order_date": -1}},
                        {"$limit": 50}
                    ]
                }

        # Intent: "did all users/customers have at least 1 order?"
        # In this schema, orders.user references customers._id (not users._id).
        if (not is_complex_request) and ("order" in q) and ("all users" in q or "all customers" in q or "at least 1" in q or "atleast 1" in q):
            asks_for_names = ("name" in q) or ("names" in q) or ("show me" in q and "customer" in q)
            if asks_for_names:
                return {
                    "collection": "customers",
                    "operation": "aggregate",
                    "pipeline": [
                        {
                            "$lookup": {
                                "from": "orders",
                                "localField": "_id",
                                "foreignField": "user",
                                "as": "orders_data"
                            }
                        },
                        {"$match": {"orders_data": {"$eq": []}}},
                        {
                            "$project": {
                                "_id": 0,
                                "customer_name": {
                                    "$trim": {
                                        "input": {
                                            "$concat": [
                                                {"$ifNull": ["$first_name", ""]},
                                                " ",
                                                {"$ifNull": ["$last_name", ""]}
                                            ]
                                        }
                                    }
                                },
                                "email": {"$ifNull": ["$email", ""]}
                            }
                        },
                        {"$sort": {"customer_name": 1}},
                        {"$limit": 500}
                    ]
                }
            return {
                "collection": "customers",
                "operation": "aggregate",
                "pipeline": [
                    {
                        "$lookup": {
                            "from": "orders",
                            "localField": "_id",
                            "foreignField": "user",
                            "as": "orders_data"
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "total_customers": {"$sum": 1},
                            "customers_without_orders": {
                                "$sum": {
                                    "$cond": [
                                        {"$eq": [{"$size": "$orders_data"}, 0]},
                                        1,
                                        0
                                    ]
                                }
                            }
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "total_customers": 1,
                            "customers_without_orders": 1,
                            "all_customers_have_orders": {"$eq": ["$customers_without_orders", 0]}
                        }
                    }
                ]
            }

        # Intent: total quantity sold per product.
        if (not is_complex_request) and ("product" in q) and ("quantity sold" in q or "total quantity sold" in q or "units sold" in q):
            return {
                "collection": "orders",
                "operation": "aggregate",
                "pipeline": [
                    {"$unwind": "$items"},
                    {
                        "$lookup": {
                            "from": "products",
                            "localField": "items.product",
                            "foreignField": "_id",
                            "as": "product_info"
                        }
                    },
                    {"$unwind": {"path": "$product_info", "preserveNullAndEmptyArrays": False}},
                    {
                        "$group": {
                            "_id": "$product_info.name",
                            "totalQuantitySold": {"$sum": "$items.quantity"}
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "productName": "$_id",
                            "totalQuantitySold": 1
                        }
                    },
                    {"$sort": {"totalQuantitySold": -1}},
                    {"$limit": 1000}
                ]
            }

        # Intent: shipped orders per month (typically for line chart/trend).
        if (not is_complex_request) and ("order" in q) and ("month" in q) and ("ship" in q):
            return {
                "collection": "orders",
                "operation": "aggregate",
                "pipeline": [
                    {"$match": {"status": "shipped"}},
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": "%Y-%m",
                                    "date": "$order_date"
                                }
                            },
                            "count": {"$sum": 1}
                        }
                    },
                    {"$project": {"_id": 0, "month": "$_id", "count": 1}},
                    {"$sort": {"month": 1}}
                ]
            }

        # Intent: orders placed by customers from a given state/country.
        if (not is_complex_request) and ("order" in q) and ("customer" in q) and (" from " in q):
            loc_match = re.search(r"(?:customers?\s+from|from)\s+([a-zA-Z][a-zA-Z\\s\\-]{1,40})(?:\\b|$)", natural_query, re.IGNORECASE)
            location = loc_match.group(1).strip() if loc_match else ""
            # Remove common trailing words that can be captured in free-form prompts.
            location = re.split(r"\b(with|show|list|get|and|who|that)\b", location, flags=re.IGNORECASE)[0].strip()

            if location:
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
                        {"$unwind": {"path": "$customer_info", "preserveNullAndEmptyArrays": False}},
                        {
                            "$match": {
                                "$or": [
                                    {"customer_info.address.state": {"$regex": f"^{re.escape(location)}$", "$options": "i"}},
                                    {"customer_info.address.country": {"$regex": f"^{re.escape(location)}$", "$options": "i"}}
                                ]
                            }
                        },
                        {"$sort": {"order_date": -1}},
                        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": True}},
                        {
                            "$lookup": {
                                "from": "products",
                                "localField": "items.product",
                                "foreignField": "_id",
                                "as": "product_info"
                            }
                        },
                        {"$unwind": {"path": "$product_info", "preserveNullAndEmptyArrays": True}},
                        {
                            "$group": {
                                "_id": "$_id",
                                "order_date": {"$first": "$order_date"},
                                "status": {"$first": "$status"},
                                "total_amount": {"$first": "$total_amount"},
                                "customer_name": {"$first": {"$concat": ["$customer_info.first_name", " ", "$customer_info.last_name"]}},
                                "customer_email": {"$first": "$customer_info.email"},
                                "customer_state": {"$first": "$customer_info.address.state"},
                                "customer_country": {"$first": "$customer_info.address.country"},
                                "product_names": {"$addToSet": "$product_info.name"}
                            }
                        },
                        {
                            "$project": {
                                "_id": 0,
                                "order_id": "$_id",
                                "order_date": 1,
                                "status": 1,
                                "total_amount": 1,
                                "customer_name": 1,
                                "customer_email": 1,
                                "customer_state": 1,
                                "customer_country": 1,
                                "product_names": {
                                    "$filter": {
                                        "input": "$product_names",
                                        "as": "pn",
                                        "cond": {"$ne": ["$$pn", None]}
                                    }
                                }
                            }
                        },
                        {"$sort": {"order_date": -1}},
                        {"$limit": 200}
                    ]
                }

        # Intent: total stock quantity per category, optionally with country.
        wants_stock = ("stock" in q) and ("category" in q)
        wants_country = "country" in q
        if (not is_complex_request) and wants_stock:
            product_schema = self._get_collection_schema("products")
            category_schema = self._get_collection_schema("categories")
            product_fields = set(product_schema.get("fields", []))
            category_fields = set(category_schema.get("fields", []))

            if "products" in self.collections and "categories" in self.collections and "category" in product_fields:
                stock_field = "stock" if "stock" in product_fields else None
                if not stock_field:
                    # Try reasonable alternates if dataset differs
                    for cand in ["stock_quantity", "inventory", "quantity", "inventory_count"]:
                        if cand in product_fields:
                            stock_field = cand
                            break

                if stock_field:
                    country_field = None
                    for cand in ["country", "country_name", "origin_country"]:
                        if cand in product_fields:
                            country_field = cand
                            break

                    group_id = {"category_name": "$category_info.name"}
                    if wants_country and country_field:
                        group_id["country"] = f"${country_field}"

                    label_expr = "$_id.category_name"
                    if wants_country and country_field:
                        label_expr = {
                            "$concat": [
                                "$_id.category_name",
                                " - ",
                                {"$ifNull": [f"$_id.country", "Unknown"]}
                            ]
                        }

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
                            {"$unwind": {"path": "$category_info", "preserveNullAndEmptyArrays": True}},
                            {
                                "$group": {
                                    "_id": group_id,
                                    "total_stock": {"$sum": f"${stock_field}"}
                                }
                            },
                            {
                                "$project": {
                                    "_id": 0,
                                    "label": label_expr,
                                    "value": "$total_stock"
                                }
                            },
                            {"$sort": {"value": -1}},
                            {"$limit": 50}
                        ]
                    }

        # Intent: total delivered product count + total revenue from delivered orders
        delivered_tokens = ["delivered", "delivery"]
        wants_products = ("product count" in q) or ("products count" in q) or ("product total" in q) or ("total delivered product" in q)
        wants_revenue = ("revenue" in q) or ("total amount" in q) or ("sales" in q)
        if (not is_complex_request) and any(tok in q for tok in delivered_tokens) and wants_products and wants_revenue:
            return {
                "collection": "orders",
                "operation": "aggregate",
                "pipeline": [
                    {"$match": {"status": "delivered"}},
                    {
                        "$facet": {
                            "revenue": [
                                {"$group": {"_id": None, "totalRevenue": {"$sum": "$total_amount"}}}
                            ],
                            "products": [
                                {"$unwind": "$items"},
                                {"$group": {"_id": None, "totalDeliveredProductCount": {"$sum": "$items.quantity"}}}
                            ]
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "totalRevenue": {"$ifNull": [{"$arrayElemAt": ["$revenue.totalRevenue", 0]}, 0]},
                            "totalDeliveredProductCount": {"$ifNull": [{"$arrayElemAt": ["$products.totalDeliveredProductCount", 0]}, 0]}
                        }
                    }
                ]
            }

        # Intent: most recent orders with status and total amount
        if (not is_complex_request) and ("recent orders" in q or "most recent orders" in q or "latest orders" in q) and ("status" in q) and ("total amount" in q or "amount" in q):
            limit = 10
            m = re.search(r"\b(\d+)\b", q)
            if m:
                try:
                    limit = max(1, min(int(m.group(1)), 100))
                except Exception:
                    pass
            return {
                "collection": collection_hint or "orders",
                "operation": "find",
                "query": {},
                "projection": {"status": 1, "total_amount": 1, "order_date": 1, "_id": 0},
                "sort": {"order_date": -1},
                "limit": limit
            }

        return None

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
