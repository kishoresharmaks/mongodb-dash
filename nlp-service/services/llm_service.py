import os
from typing import Any, Dict
from config import settings

def create_llm():
    """
    Factory function to create LLM instance based on provider setting.
    Supports OpenAI, Google Gemini, and Local LLM via LM Studio.
    """
    provider = settings.llm_provider.lower()
    
    print(f"🤖 Initializing LLM Provider: {provider}")
    
    if provider == "openai":
        return create_openai_llm()
    elif provider == "gemini":
        return create_gemini_llm()
    elif provider == "local":
        return create_local_llm()
    elif provider == "huggingface":
        return create_huggingface_llm()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Use 'openai', 'gemini', 'local', or 'huggingface'")

def create_openai_llm():
    """Create OpenAI LLM instance"""
    try:
        from langchain_openai import ChatOpenAI
        
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when using OpenAI provider")
        
        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            openai_api_key=settings.openai_api_key,
            max_retries=2,
            timeout=120
        )
        
        print(f"✅ OpenAI LLM initialized: {settings.openai_model}")
        return llm, {
            "provider": "openai",
            "model": settings.openai_model
        }
    except ImportError:
        raise ImportError("langchain-openai not installed. Run: pip install langchain-openai")
    except Exception as e:
        raise Exception(f"Failed to initialize OpenAI LLM: {str(e)}")

def create_gemini_llm():
    """Create Google Gemini LLM instance using modern google-genai SDK"""
    try:
        from google import genai
        
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when using Gemini provider")
        
        # Wrapper to maintain compatibility with the agent's LangChain-style .invoke() call
        class GeminiNativeLLM:
            def __init__(self, api_key: str, model_name: str):
                self.client = genai.Client(api_key=api_key)
                self.model_name = model_name
            
            def invoke(self, messages):
                system_instruction = None
                contents = []
                
                for msg in messages:
                    # Detect role and content
                    content = getattr(msg, 'content', str(msg))
                    msg_type = getattr(msg, 'type', 'human')
                    
                    if msg_type == 'system':
                        system_instruction = content
                    else:
                        contents.append(content)
                
                # Call native SDK
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config={
                        'system_instruction': system_instruction,
                        'temperature': 0.0
                    }
                )
                
                # Mock AIMessage
                class AIMessageMock:
                    def __init__(self, text):
                        self.content = text
                
                return AIMessageMock(response.text)

        llm = GeminiNativeLLM(settings.google_api_key, settings.gemini_model)
        
        print(f"✅ Google Gemini (Native SDK) initialized: {settings.gemini_model}")
        return llm, {
            "provider": "gemini",
            "model": settings.gemini_model,
            "sdk": "google-genai"
        }
    except ImportError:
        print("⚠️ google-genai not installed. Run: pip install google-genai")
        raise ImportError("google-genai not installed. Run: pip install google-genai")
    except Exception as e:
        raise Exception(f"Failed to initialize Gemini LLM: {str(e)}")

def create_local_llm():
    """Create Local LLM instance via LM Studio"""
    try:
        from langchain_openai import ChatOpenAI
        
        llm = ChatOpenAI(
            base_url=settings.local_llm_base_url,
            model=settings.local_llm_model,
            api_key="not-needed",  # LM Studio doesn't require API key
            temperature=0,
            max_retries=2,
            timeout=120
        )
        
        print(f"✅ Local LLM initialized: {settings.local_llm_model}")
        print(f"   Base URL: {settings.local_llm_base_url}")
        return llm, {
            "provider": "local",
            "model": settings.local_llm_model
        }
    except Exception as e:
        raise Exception(f"Failed to initialize Local LLM: {str(e)}. Ensure LM Studio is running.")

def create_huggingface_llm():
    """Create Hugging Face LLM instance via Inference API"""
    try:
        from huggingface_hub import InferenceClient
        
        if not settings.huggingface_api_key or settings.huggingface_api_key == "your-hf-token-here":
            raise ValueError("HUGGINGFACE_API_KEY is required when using HuggingFace provider")
        
        class HuggingFaceNativeLLM:
            def __init__(self, api_key: str, model_name: str):
                self.client = InferenceClient(model=model_name, token=api_key)
            
            def invoke(self, messages):
                hf_messages = []
                for msg in messages:
                    # Get content
                    content = getattr(msg, 'content', str(msg))
                    
                    # Map LangChain message types to HF role names
                    # LangChain types: 'system', 'human', 'ai'
                    msg_type = getattr(msg, 'type', 'human')
                    
                    if msg_type == 'system':
                        role = 'system'
                    elif msg_type == 'human':
                        role = 'user'
                    elif msg_type == 'ai':
                        role = 'assistant'
                    else:
                        role = 'user'
                        
                    hf_messages.append({"role": role, "content": content})
                
                # Call Inference API with structured messages
                response = self.client.chat_completion(
                    messages=hf_messages,
                    max_tokens=1024,
                    temperature=0.1
                )
                
                class AIMessageMock:
                    def __init__(self, text):
                        self.content = text
                
                return AIMessageMock(response.choices[0].message.content)

        llm = HuggingFaceNativeLLM(settings.huggingface_api_key, settings.huggingface_model)
        
        print(f"✅ Hugging Face (Native Client) initialized: {settings.huggingface_model}")
        return llm, {
            "provider": "huggingface",
            "model": settings.huggingface_model,
            "sdk": "huggingface_hub"
        }
    except ImportError:
        raise ImportError("huggingface_hub not installed. Run: pip install huggingface_hub")
    except Exception as e:
        raise Exception(f"Failed to initialize Hugging Face LLM: {str(e)}")

def get_llm_metadata(provider: str, model: str) -> Dict[str, Any]:
    """Get metadata about the current LLM configuration"""
    return {
        "provider": provider,
        "model": model,
        "supports_streaming": True,
        "max_tokens": 4096 if provider == "local" else 8192
    }
