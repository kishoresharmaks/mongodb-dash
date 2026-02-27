import re
from typing import Dict, Any
from config import settings

def validate_natural_query(query: str) -> tuple[bool, str]:
    """
    Validate natural language query for safety and format.
    
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check length
    if not query or len(query.strip()) == 0:
        return False, "Query cannot be empty"
    
    if len(query) > settings.max_query_length:
        return False, f"Query cannot exceed {settings.max_query_length} characters"
    
    # Check for SQL injection patterns (basic)
    sql_patterns = [
        r";\s*drop\s+",
        r";\s*truncate\s+",
        r"union\s+select",
        r"exec\s*\(",
        r"execute\s*\("
    ]
    
    query_lower = query.lower()
    for pattern in sql_patterns:
        if re.search(pattern, query_lower):
            return False, "Query contains potentially dangerous patterns"
    
    return True, ""

def validate_mql_safety(mql: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate MongoDB query for dangerous operations.
    
    Returns:
        tuple: (is_safe, error_message)
    """
    if not isinstance(mql, dict):
        return True, ""  # Not a dict, let MongoDB handle it
    
    # Dangerous operators to block anywhere in payload
    dangerous_ops = [
        "$drop",
        "$dropDatabase",
        "$eval",
        "$where"
    ]
    
    # Convert to string for easier checking
    mql_str = str(mql).lower()
    
    for op in dangerous_ops:
        if op.lower() in mql_str:
            return False, f"Dangerous operation '{op}' is not allowed"

    # Only read operations are allowed in this application flow
    operation = str(mql.get("operation", "find")).lower()
    if operation not in {"find", "aggregate"}:
        return False, f"Operation '{operation}' is not allowed. Only 'find' and 'aggregate' are supported."
    
    return True, ""

def sanitize_query(query: str) -> str:
    """
    Sanitize natural language query by removing potentially harmful characters.
    """
    # Remove control characters
    query = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', query)
    
    # Trim whitespace
    query = query.strip()
    
    return query
