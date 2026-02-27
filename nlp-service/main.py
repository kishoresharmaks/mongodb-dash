from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
import uvicorn
from contextlib import asynccontextmanager

from config import settings
from agents.mongodb_agent import MongoDBNLAgent
from utils.validators import validate_natural_query, sanitize_query

# Global agent instance
agent: Optional[MongoDBNLAgent] = None


def _apply_request_database(database: Optional[str]) -> None:
    """Apply per-request database context when provided."""
    if not agent or not database:
        return
    agent.set_database(database)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    global agent

    # Startup
    print("\n" + "=" * 60)
    print("Starting NLP Service for MongoDB")
    print("=" * 60)
    print(f"Database: {settings.database_name}")
    print(f"LLM Provider: {settings.llm_provider}")
    print("=" * 60 + "\n")

    try:
        agent = MongoDBNLAgent(
            connection_string=settings.mongodb_atlas_uri,
            database_name=settings.database_name
        )
        print("MongoDB NL Agent initialized successfully\n")
    except Exception as e:
        print(f"Failed to initialize agent: {e}\n")
        raise

    yield

    # Shutdown
    if agent:
        agent.close()
    print("\nNLP Service shutting down\n")


# Create FastAPI app
app = FastAPI(
    title="NLP MongoDB Service",
    description="Natural Language Interface for MongoDB using LLMs",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query", min_length=1, max_length=5000)
    database: Optional[str] = Field(None, description="Database name (optional)")
    collection: Optional[str] = Field(None, description="Collection name (optional)")
    history: Optional[List[Dict[str, str]]] = Field(None, description="Chat history (optional)")
    permissions: Optional[Dict[str, Any]] = Field(None, description="Role-based permissions (optional)")
    userRole: Optional[str] = Field(None, description="User role name (optional)")
    policyName: Optional[str] = Field(None, description="Role policy name (optional)")
    customSystemPrompt: Optional[str] = Field(None, description="Custom base system prompt (optional)")
    visualizationHint: Optional[Dict[str, Any]] = Field(None, description="User's explicit chart type preference (optional)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Show movies from 1999 with rating above 8",
                "database": "sample_mflix",
                "collection": "movies",
                "userRole": "admin",
                "policyName": "Manager",
                "history": [
                    {"role": "user", "content": "Show me horror movies"},
                    {"role": "assistant", "content": "I found 50 horror movies."}
                ]
            }
        }
    )


class ExecuteMQLRequest(BaseModel):
    mql: Dict[str, Any] = Field(..., description="The MQL query to execute")
    database: Optional[str] = Field(None, description="Database name (optional)")
    permissions: Optional[Dict[str, Any]] = Field(None, description="Role-based permissions (optional)")


class QueryResponse(BaseModel):
    success: bool
    mql_query: Optional[Dict[str, Any]] = None
    results: List[Dict[str, Any]] = []
    collection: Optional[str] = None
    explanation: str
    needs_confirmation: bool = False
    type: Optional[str] = None
    chart_type: Optional[str] = None
    title: Optional[str] = None
    x_key: Optional[str] = None
    y_key: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    service: str
    llm_provider: str
    llm_model: str
    database: str


# Routes
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "service": "NLP MongoDB Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "translate": "/translate (POST)",
            "plan": "/plan (POST)",
            "execute-mql": "/execute-mql (POST)",
            "docs": "/docs"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return {
        "status": "healthy",
        "service": "NLP MongoDB Service",
        "llm_provider": agent.llm_metadata["provider"],
        "llm_model": agent.llm_metadata["model"],
        "database": agent.database_name
    }


@app.get("/metadata/collections", tags=["Metadata"])
async def get_collections():
    """Get list of available collections"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return {"collections": agent.collections, "database": agent.database_name}


@app.post("/translate", response_model=QueryResponse, tags=["Query"])
async def translate_query(request: QueryRequest):
    """
    Translate natural language query to MongoDB query and execute it.
    """
    print(f"\nReceived Request: '{request.query}'")

    if not agent:
        print("Error: Agent not initialized!")
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        _apply_request_database(request.database)

        # Sanitize query
        print("Sanitizing query...")
        sanitized_query = sanitize_query(request.query)

        # Validate query
        print("Validating query...")
        is_valid, error_msg = validate_natural_query(sanitized_query)
        if not is_valid:
            print(f"Validation failed: {error_msg}")
            return QueryResponse(
                success=False,
                explanation=f"Invalid query: {error_msg}",
                error=error_msg,
                metadata={"provider": agent.llm_metadata["provider"]}
            )

        # Process query
        print("Sending to MongoDB NL Agent...")
        result = agent.process_query(
            natural_query=sanitized_query,
            collection=request.collection,
            history=request.history,
            permissions=request.permissions,
            user_role=request.userRole,
            policy_name=request.policyName,
            custom_system_prompt=request.customSystemPrompt
        )

        print(f"Processing complete. Success: {result.get('success')}")
        return QueryResponse(**result)

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in translate endpoint: {e}")
        traceback.print_exc()
        return QueryResponse(
            success=False,
            explanation=f"Error processing query: {str(e)}",
            error=str(e),
            metadata={"provider": agent.llm_metadata["provider"] if agent else "unknown"}
        )


@app.post("/plan", response_model=QueryResponse, tags=["Query"])
async def plan_query(request: QueryRequest):
    """
    Generate a query plan without executing it.
    """
    print(f"\nReceived Plan Request: '{request.query}'")

    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        _apply_request_database(request.database)

        sanitized_query = sanitize_query(request.query)
        is_valid, error_msg = validate_natural_query(sanitized_query)
        if not is_valid:
            return QueryResponse(
                success=False,
                explanation=f"Invalid query: {error_msg}",
                error=error_msg,
                metadata={"provider": agent.llm_metadata["provider"]}
            )

        result = agent.generate_query_plan(
            natural_query=sanitized_query,
            collection=request.collection,
            history=request.history,
            permissions=request.permissions,
            user_role=request.userRole,
            policy_name=request.policyName,
            custom_system_prompt=request.customSystemPrompt,
            visualization_hint=request.visualizationHint
        )

        return QueryResponse(**result)
    except Exception as e:
        return QueryResponse(
            success=False,
            explanation=f"Error generating plan: {str(e)}",
            error=str(e),
            metadata={"provider": agent.llm_metadata["provider"]}
        )


@app.post("/execute-mql", response_model=QueryResponse, tags=["Query"])
async def execute_mql_confirmed(request: ExecuteMQLRequest):
    """
    Execute a confirmed MQL query.
    """
    print("\nReceived Execution Request for MQL")

    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        _apply_request_database(request.database)
        result = agent.execute_mql(
            request.mql,
            permissions=request.permissions
        )

        return QueryResponse(
            success=True,
            mql_query=request.mql,
            results=result["results"],
            explanation=f"Successfully executed query. Found {len(result['results'])} results.",
            metadata=result["metadata"]
        )
    except Exception as e:
        return QueryResponse(
            success=False,
            explanation=f"Error executing confirmed query: {str(e)}",
            error=str(e),
            metadata={"provider": agent.llm_metadata["provider"]}
        )


# Run server
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower()
    )
