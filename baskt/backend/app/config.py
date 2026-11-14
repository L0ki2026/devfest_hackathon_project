from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    demo_mode: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    fdc_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FDC_API_KEY", "USDA_API_KEY"),
    )
    frontend_origins: str = "http://localhost:3000,http://localhost:5173"
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    usda_timeout_seconds: float = 30.0
    max_basket_items: int = 100
    max_upload_bytes: int = 10 * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.strip())

    def usda_configured(self) -> bool:
        return bool(self.fdc_api_key and self.fdc_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()