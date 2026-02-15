import logging

import betterlogging as bl
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.handlers import start, site, group, link
from bot.tasks.parse import  parse_satu_groups, parse_olx_groups
from core.config import load_config


def setup_logging():
    """Настройка конфигурации ведения журнала для приложения.

    Этот метод инициализирует конфигурацию ведения журнала для приложения.
    Он устанавливает уровень журнала INFO и настраивает базовый цветной журнал для
    вывода. Формат журнала включает имя файла, номер строки, уровень журнала,
    временную метку, имя регистратора и сообщение журнала.

    Возвращает:
        None

    Пример использования:
        setup_logging()

    """
    log_level = logging.INFO
    bl.basic_colorized_config(level = log_level)

    logging.basicConfig(
        level = logging.INFO,
        format = "%(filename)s:%(lineno)d #%(levelname)-8s [%(asctime)s] - %(name)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("Запуск бота")


async def main():
    setup_logging()

    config = load_config()
    dp = Dispatcher(storage = MemoryStorage())

    scheduler = AsyncIOScheduler(timezone = 'Europe/Moscow')
    scheduler.add_job(parse_satu_groups, trigger = 'cron', hour = 9, minute = 3)
    scheduler.add_job(parse_olx_groups, trigger='interval', minutes=5)
    scheduler.start()

    # Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(site.router)
    dp.include_router(group.router)
    dp.include_router(link.router)

    bot = Bot(
        token = config.tg_bot.token,
        default = DefaultBotProperties(parse_mode = "HTML"),

    )

    await dp.start_polling(bot)
