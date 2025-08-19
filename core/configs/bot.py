from dataclasses import dataclass

from decouple import config


@dataclass
class TgBot:
    """Создает объект TgBot из переменных среды."""

    token: str
    admin_ids: list[int]

    @staticmethod
    def from_env(env: config):
        """Создает объект TgBot из переменных среды."""
        token = env("BOT_TOKEN")
        admin_ids = [int(x) for x in config("ADMINS").split(",")]
        return TgBot(token = token, admin_ids = admin_ids)
