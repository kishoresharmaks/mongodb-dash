from typing import Dict, Any

def optimize_mql(mql: Dict[str, Any], default_limit: int = 100) -> Dict[str, Any]:
    """
    Optimize MongoDB query by adding sensible defaults.
    
    Args:
        mql: MongoDB query object
        default_limit: Default limit to apply if not present
    
    Returns:
        Optimized MQL query
    """
    if not isinstance(mql, dict):
        return mql
    
    # Add default limit if not present
    if "limit" not in mql and "aggregate" not in str(mql):
        mql["limit"] = default_limit
    
    # Optimize projection if possible
    if "projection" in mql and isinstance(mql["projection"], dict):
        # Ensure _id is included unless explicitly excluded
        if "_id" not in mql["projection"]:
            mql["projection"]["_id"] = 1
    
    return mql

def add_query_hints(query: str, mql: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add query hints based on natural language patterns.
    
    Args:
        query: Natural language query
        mql: MongoDB query object
    
    Returns:
        MQL with hints added
    """
    query_lower = query.lower()
    
    # Add sort if query mentions ordering
    if any(word in query_lower for word in ["top", "best", "highest", "most"]):
        if "sort" not in mql:
            # Try to infer sort field from context
            if "rating" in query_lower:
                mql["sort"] = {"rating": -1}
            elif "price" in query_lower or "revenue" in query_lower:
                mql["sort"] = {"price": -1}
            elif "date" in query_lower or "recent" in query_lower:
                mql["sort"] = {"date": -1}
    
    # Add limit for "top N" queries
    if "top" in query_lower:
        import re
        match = re.search(r'top\s+(\d+)', query_lower)
        if match:
            limit = int(match.group(1))
            mql["limit"] = min(limit, 100)  # Cap at 100
    
    return mql

def format_mql_for_display(mql: Dict[str, Any]) -> str:
    """
    Format MQL query for user-friendly display.
    
    Args:
        mql: MongoDB query object
    
    Returns:
        Formatted string representation
    """
    import json
    try:
        return json.dumps(mql, indent=2, default=str)
    except:
        return str(mql)
