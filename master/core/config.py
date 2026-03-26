from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Project Nebula"
    DATABASE_URL: str = "postgresql+asyncpg://nebula:nebula_password@localhost:5432/nebula_db"
    
    class Config:
        env_file = ".env"

settings = Settings()
