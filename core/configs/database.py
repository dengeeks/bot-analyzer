from dataclasses import dataclass

from decouple import config
from tortoise import Tortoise

from bot.database.models.site import Site


@dataclass
class DbConfig:
    """Класс конфигурации базы данных. Этот класс содержит настройки
    базы данных, такие как хост, пароль, порт и т. д.

    Атрибуты
    ----------
    host : str
        Хост, на котором расположен сервер базы данных.
    password : str
        Пароль, используемый для аутентификации в базе данных.
    user : str
        Имя пользователя, используемое для аутентификации в базе данных.
    database : str
        Имя базы данных.
    port : int
        Порт, который прослушивает сервер базы данных.

    """

    host: str
    password: str
    user: str
    database: str
    port: int = 5432

    def construct_tortoise_url(self, driver = "asyncpg", host = None, port = None) -> str:
        """Создаёт и возвращает URL-адрес TortoiseORM для этой конфигурации базы данных."""
        if not host:
            host = self.host
        if not port:
            port = self.port
        return f"{driver}://{self.user}:{self.password}@{host}:{port}/{self.database}"

    @staticmethod
    def from_env(env: config):
        """Создает объект DbConfig из переменных среды."""
        host = env("DB_HOST")
        password = env("POSTGRES_PASSWORD")
        user = env("POSTGRES_USER")
        database = env("POSTGRES_DB")
        port = env("DB_PORT", 5432)
        return DbConfig(
            host = host,
            password = password,
            user = user,
            database = database,
            port = port,
        )


async def init_tortoise(db: DbConfig, modules: dict):
    """Инициализирует Tortoise ORM с заданной конфигурацией базы данных и
    модулями.

    Параметры
    ----------
    db : DbConfig
        Конфигурация базы данных.
    modules : dict
        Словарь, содержащий конфигурации модулей.

    """
    tortoise_url = db.construct_tortoise_url()
    await Tortoise.init(
        db_url = tortoise_url,
        modules = modules,
    )
    await Tortoise.generate_schemas()

    # Создаём дефолтный сайт только если его ещё нет
    await Site.get_or_create(
        title = "SATU KZ"
    )


async def close_tortoise():
    """Closes Tortoise ORM connections."""
    await Tortoise.close_connections()


TORTOISE_ORM = {
    "connections": {"default": DbConfig.from_env(config).construct_tortoise_url()},
    "apps": {
        "models": {
            "models": [
                "bot.database.models.user",
                "bot.database.models.product_group",
                "bot.database.models.price_history",
                "bot.database.models.product_link",
                "bot.database.models.site",
                "aerich.models"
            ],
            "default_connection": "default",
        },
    },
}
