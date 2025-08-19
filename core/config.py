from dataclasses import dataclass
from typing import Optional

from decouple import config

from core.configs.bot import TgBot
from core.configs.database import DbConfig


@dataclass
class Config:
    """Основной класс конфигурации, объединяющий все остальные классы конфигурации.

    Этот класс содержит другие классы конфигурации, обеспечивая централизованную точку доступа ко всем настройкам.

    Атрибуты
    ----------
    tg_bot : TgBot
        Содержит настройки, связанные с Telegram-ботом.
    db : Необязательно[DbConfig]
        Содержит настройки, относящиеся к базе данных (по умолчанию — None).

    """

    tg_bot: TgBot
    db: Optional[DbConfig] = None


def load_config() -> Config:
    """возвращает объект Config."""

    return Config(
        tg_bot = TgBot.from_env(config),
        db = DbConfig.from_env(config),
    )
