from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

from dotenv import load_dotenv
import os
load_dotenv() 
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

key = os.getenv("GROQ_API_KEY")

print("Groq key loaded:", bool(key))
print("Groq key prefix:", key[:8] if key else None)
print("Groq key length:", len(key) if key else 0)

class Settings(BaseSettings):
    app_name: str = "StockAI"
    app_env: str = "development"
    app_debug: bool = True
    api_version_prefix: str = "/v1"
    # frontend_url: str = "htt p://localhost:5173"
    # jwt_secret_key: str
    # jwt_algorithm: str = "HS256"
    # jwt_access_token_expire_minutes: int = 10080
    # database_url: str
    # redis_url: str = "redis://redis:6379/0"
    # openrouter_api_key: str = ""
    # openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # openrouter_default_model: str = "openai/gpt-4o-mini"
    # openrouter_app_name: str = "ONEAI"
    # openrouter_site_url: str = "http://localhost:5173"
    # tavily_api_key: str = ""
    # serpapi_key: str = ""
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Returns cached settings so the app reads environment once per process.
@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()