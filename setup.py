import asyncio
import logging

from decouple import config
from tortoise import run_async

from bot.main import main
from core.configs.database import DbConfig, init_tortoise

if __name__ == "__main__":
    db_config = DbConfig.from_env(config)
    modules = {
        "models": [
            "bot.database.models.user",
            "bot.database.models.product_group",
            "bot.database.models.price_history",
            "bot.database.models.product_link",
            "bot.database.models.site",
        ]
    }
    run_async(init_tortoise(db_config, modules))
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("The bot has been disabled!")
