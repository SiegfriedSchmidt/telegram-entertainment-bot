from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, JsonConfigSettingsSource
from pydantic import SecretStr
from typing import Type, Tuple, List
from lib.init import settings_file_path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(json_file=settings_file_path, json_file_encoding='utf-8', extra='allow')
    main_group_id: int
    group_ids: List[int]
    admin_ids: List[int]
    notification_ids: List[int]
    bot_token: SecretStr
    gemini_api_key: SecretStr
    otp_secret: SecretStr
    server_video_url: str = ''
    proxy_url: str = ''
    day_start_time: str = '11:00'

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: Type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            JsonConfigSettingsSource(settings_cls),
            env_settings,
            file_secret_settings,
        )


config = Settings()
