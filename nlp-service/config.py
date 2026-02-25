import os
from typing import Optional
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # MongoDB Configuration
    mongodb_atlas_uri: str
    database_name: str = "sample_shop"
    
    # LLM Provider Selection
    llm_provider: str = "gemini"  # Options: openai, gemini, local, huggingface
    
    # OpenAI Configuration
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-3.5-turbo"
    
    # Google Gemini Configuration
    google_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash-lite"
    
    # Hugging Face Configuration
    huggingface_api_key: Optional[str] = None
    huggingface_model: str = "openai/gpt-oss-120b"
    
    # Local LLM Configuration
    local_llm_base_url: str = "http://10.1.22.84:1234/v1"
    local_llm_model: str = "google/gemma-3-27b"
    
    # Service Configuration
    port: int = 8000
    max_query_length: int = 5000
    log_level: str = "INFO"
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False
    )

# Global settings instance
settings = Settings()
