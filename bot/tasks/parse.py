import asyncio
import io
import logging
from datetime import datetime
from typing import List, Dict, Optional, Union

import aiohttp
import pandas as pd
from aiogram import Bot
from aiogram.types import BufferedInputFile
from openpyxl.utils import get_column_letter
from parsel import Selector
from tortoise.transactions import in_transaction

from bot.database.models.price_history import PriceHistory
from bot.database.models.product_group import ProductGroup
from core.config import load_config

logger = logging.getLogger(__name__)
config = load_config()
bot = Bot(token = config.tg_bot.token)


class ProductParser:
    MAX_RETRIES = 3
    REQUEST_DELAY = 0.1  # seconds

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch(self, url: str) -> Optional[str]:
        """Асинхронный запрос с повторными попытками и обработкой ошибок."""
        for attempt in range(self.MAX_RETRIES):
            try:
                async with self.session.get(url, timeout = aiohttp.ClientTimeout(total = 10)) as response:
                    response.raise_for_status()
                    return await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"[{url}] Попытка {attempt + 1} не удалась: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.REQUEST_DELAY * (attempt + 1))
        logger.error(f"[{url}] Не удалось получить страницу после {self.MAX_RETRIES} попыток")
        return None

    @staticmethod
    def extract(selector: Selector, xpath: str, default: str = "") -> str:
        """Безопасное извлечение данных по XPath."""
        try:
            value = selector.xpath(xpath).get()
            return value.strip() if value else default
        except Exception as e:
            logger.warning(f"Ошибка XPath '{xpath}': {e}")
            return default

    async def parse_product(self, url: str) -> Optional[Dict[str, Union[str, float]]]:
        """Парсинг страницы продукта."""
        html = await self.fetch(url)
        if not html:
            return None

        selector = Selector(html)
        return {
            "link": url,
            "title": self.extract(selector, "//h1[@data-qaid='product_name']/text()"),
            "price": self.extract(selector, "//div[@class='tqUsL']//div/@data-qaprice"),
            "company": self.extract(selector, "//div[@class='l-GwW fvQVX']/a[@data-qaid='company_name']/text()"),
        }


async def generate_excel(data: List[Dict]) -> io.BytesIO:
    """Генерация Excel-файла из списка словарей."""
    df = pd.DataFrame(data)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine = "openpyxl") as writer:
        df.to_excel(writer, index = False, sheet_name = "Отчёт")
        worksheet = writer.sheets["Отчёт"]

        # Автоширина колонок
        for col in worksheet.columns:
            max_length = max((len(str(cell.value)) for cell in col), default = 10)
            worksheet.column_dimensions[get_column_letter(col[0].column)].width = (max_length + 2) * 1.2

    output.seek(0)
    return output


async def process_group(group: ProductGroup, parser: ProductParser):
    """Парсинг ссылок группы, обновление базы и отправка Excel пользователю."""
    logger.info(f"Обрабатываю группу '{group.title}' (id={group.id})")
    data = []
    total_links = len(group.product_links)
    parsed_links = 0

    async with in_transaction() as conn:
        for link in group.product_links:
            product = await parser.parse_product(link.url)
            if not product:
                logger.warning(f"Не удалось спарсить {link.url}")
                continue

            # Обновление полей
            link.productName = product.get("title") or link.productName
            link.companyName = product.get("company") or link.companyName

            # Обработка цены
            raw_price = product.get("price")

            try:
                price_value = float("".join(ch for ch in raw_price if ch.isdigit() or ch == ".")) if raw_price else 0.0
            except ValueError:
                price_value = 0.0

            link.last_price = price_value
            link.last_check = datetime.utcnow()
            await link.save(using_db = conn)

            await PriceHistory.create(
                product_link = link,
                price = int(price_value),
                date = datetime.utcnow(),
                using_db = conn
            )

            data.append(
                {
                    "Дата последней проверки": link.last_check.strftime("%d.%m.%Y"),
                    "Название товара": link.productName,
                    "Название компании": link.companyName,
                    "Стоимость": link.last_price,
                    "Ссылка": link.url,
                }
            )
            parsed_links += 1

    if data and group.user.telegram_id:
        excel_file = await generate_excel(data)
        await bot.send_document(
            chat_id = group.user.telegram_id,
            document = BufferedInputFile(excel_file.getvalue(), filename = f"{group.title}.xlsx"),
            caption = (
                f"✅ Парсинг завершён.\nВсего ссылок: {total_links}\nУспешно спарсено: {parsed_links}\n\n"
                f"Отчёт по группе: {group.title}"
            )
        )
        logger.info(f"Отчёт по группе '{group.title}' отправлен пользователю {group.user.telegram_id}")


async def parse_all_groups():
    """Запуск фонового парсера по всем активным группам."""
    logger.info("Запуск фонового парсера...")
    async with aiohttp.ClientSession() as session:
        parser = ProductParser(session)
        groups = await ProductGroup.filter(is_active = True).select_related("user").prefetch_related("product_links")

        if not groups:
            logger.info("Нет активных групп для парсинга")
            return

        for group in groups:
            await process_group(group, parser)

    logger.info("Фоновый парсинг завершён ✅")


async def parse_single_group(group_id: int):
    """Принудительный запуск парсинга только для одной группы."""
    group = await ProductGroup.get(id = group_id).select_related("user").prefetch_related("product_links")

    if not group:
        logger.warning(f"Группа с id={group_id} не найдена")
        return

    async with aiohttp.ClientSession() as session:
        parser = ProductParser(session)
        await process_group(group, parser)

    logger.info(f"Принудительный парсинг группы '{group.title}' (id={group.id}) завершён ✅")
