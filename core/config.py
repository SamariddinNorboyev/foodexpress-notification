from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    jwt_secret: str
    algorithm: str = "HS256"
    
    port: int
    database_url: str
    rabbitmq_url: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str

    class Config:
        env_file = ".env"
        # Agar .env ichida kichik/katta harf farq qilsa (PORT yoki port), 
        # Pydantic avtomat tanib olishi uchun:
        env_case_sensitive = False 

settings = Settings()