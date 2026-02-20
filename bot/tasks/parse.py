import asyncio
import io
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Union
from playwright.async_api import async_playwright
import aiohttp
import pandas as pd
from aiogram import Bot
from aiogram.types import BufferedInputFile
from openpyxl.styles import Alignment, Border, Side
from openpyxl.utils import get_column_letter
from parsel import Selector
from tortoise.transactions import in_transaction

from bot.database.models.price_history import PriceHistory
from bot.database.models.product_group import ProductGroup
from core.config import load_config

logger = logging.getLogger(__name__)
config = load_config()
bot = Bot(token=config.tg_bot.token)

import time


def format_progress(start_time: float, current: int, total: int) -> str:
    # Проценты
    percent = int((current / total) * 100) if total > 0 else 0
    # Прогресс-бар
    bar_length = 10
    filled_length = int(bar_length * current // total) if total > 0 else 0
    bar = "█" * filled_length + "░" * (bar_length - filled_length)

    # Время
    elapsed = int(time.time() - start_time)
    elapsed_str = time.strftime("%Mм %Ss", time.gmtime(elapsed))

    # Примерное оставшееся время
    if current > 0:
        estimated_total = elapsed * total // current
        remaining = estimated_total - elapsed
    else:
        remaining = 0
    remaining_str = time.strftime("%Mм %Ss", time.gmtime(remaining))

    # Формат текста
    return (
        f"⏱ Время: {elapsed_str}\n"
        f"📦 Прогресс: [{bar}] {percent}% ({current}/{total})\n"
        f"⏳ Осталось примерно: {remaining_str}"
    )


class ProductParser:
    MAX_RETRIES = 3
    REQUEST_DELAY = 0.1  # seconds

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch(self, url: str) -> Optional[str]:
        """Асинхронный запрос с повторными попытками и обработкой ошибок."""
        for attempt in range(self.MAX_RETRIES):
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
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

    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
        workbook = writer.book
        worksheet = writer.sheets['Sheet1']

        # Автоподгонка ширины столбцов и настройка высоты строк
        for column in worksheet.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            contains_company_name = False
            contains_product_name = False
            contains_url_to_product_name = False
            contains_date_name = False
            contains_price_name = False

            # Проверяем ячейки столбца
            for cell in column:
                try:
                    if cell.value is not None:
                        text = str(cell.value)
                        # Проверяем наличие "Название компании"
                        if "Название компании" in text:
                            contains_company_name = True
                        elif 'Название продукта' in text or 'Название товара' in text:
                            contains_product_name = True
                        elif 'Ссылка на товар' in text or 'Ссылка' in text:
                            contains_url_to_product_name = True
                        elif 'Дата последней проверки' in text:
                            contains_date_name = True
                        elif 'Стоимость' in text:
                            contains_price_name = True

                        # Рассчитываем длину для автоподгонки
                        line_lengths = [len(line) for line in text.split('\n')]
                        cell_max_length = max(line_lengths, default=0)
                        max_length = max(max_length, cell_max_length)

                        cell.alignment = Alignment(wrap_text=True)
                        cell.border = thin_border
                except:
                    pass

            # Устанавливаем ширину столбца
            if contains_company_name:
                adjusted_width = 23
            elif contains_product_name:
                adjusted_width = 50
            elif contains_url_to_product_name:
                adjusted_width = 100
            elif contains_date_name:
                adjusted_width = 15
            elif contains_price_name:
                adjusted_width = 15
            else:
                adjusted_width = min((max_length + 2) * 1.1, 50)  # Автоподгонка для остальных
            worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)
    return output


async def process_group(group: ProductGroup, parser: ProductParser, with_stop_button: bool = False):
    """Парсинг ссылок группы, обновление базы и отправка Excel пользователю."""
    logger.info(f"Обрабатываю группу '{group.title}' (id={group.id})")
    data = []
    total_links = len(group.product_links)
    parsed_links = 0
    last_text = None
    start_time = time.time()

    async with in_transaction() as conn:
        for idx, link in enumerate(group.product_links, start=1):
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
            link.last_check = datetime.now(timezone.utc)
            await link.save(using_db=conn)

            await PriceHistory.create(
                product_link=link,
                price=int(price_value),
                date=datetime.now(timezone.utc),
                using_db=conn
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

            progress_bar = format_progress(start_time, idx, total_links)
            new_text = f"Прогресс парсинга группы: {group.title}\n{progress_bar}"

            if group.user.telegram_id:
                try:
                    if idx == 1:
                        msg = await bot.send_message(
                            group.user.telegram_id, f"Прогресс парсинга группы: {group.title}\n{progress_bar}",
                        )
                    else:  # дальше редактируем
                        if new_text != last_text:  # 🔴 проверяем
                            await bot.edit_message_text(
                                chat_id=group.user.telegram_id,
                                message_id=msg.message_id,
                                text=new_text,
                            )
                            last_text = new_text
                except Exception as e:
                    logger.warning(f"Не удалось обновить прогресс: {e}")

    if data and group.user.telegram_id:
        excel_file = await generate_excel(data)
        await bot.send_document(
            chat_id=group.user.telegram_id,
            document=BufferedInputFile(excel_file.getvalue(), filename=f"{group.title}.xlsx"),
            caption=(
                f"✅ Парсинг завершён.\nВсего ссылок: {total_links}\nУспешно спарсено: {parsed_links}\n\n"
                f"Отчёт по группе: {group.title}"
            )
        )
        logger.info(f"Отчёт по группе '{group.title}' отправлен пользователю {group.user.telegram_id}")


async def process_olx_group(group: ProductGroup):
    """Специальный парсер для OLX через Playwright (для просмотров)."""
    logger.info(f"Запуск OLX парсера для группы '{group.title}' (id={group.id})")

    data = []
    total_links = len(group.product_links)
    parsed_links = 0
    last_text = None
    start_time = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )

        # Оставляем CSS (отключаем только картинки/видео/шрифты)
        await context.route("**/*", lambda route: route.abort()
        if route.request.resource_type in ["image", "media", "font"]
        else route.continue_()
                            )

        page = await context.new_page()

        for idx, link in enumerate(group.product_links, start=1):
            views_count = 0
            success = False

            # --- ЦИКЛ ПОВТОРОВ ДЛЯ ОДНОЙ ССЫЛКИ ---
            for attempt in range(1, 4):
                try:
                    response = await page.goto(link.url, timeout=40000)
                    content = await page.content()
                    await asyncio.sleep(8)

                    # 1. ПРОВЕРКА НА БЛОКИРОВКУ
                    if response.status == 403 or "Request blocked" in content:
                        logger.warning(f"⚠️ [Попытка {attempt}] Блок CloudFront для {link.url}. Ждем 30с...")
                        await asyncio.sleep(30)
                        continue  # Идем на следующую попытку

                    await page.evaluate("""
                                            async () => {
                                                for (let i = 0; i < 10; i++) {
                                                    window.scrollBy(0, 200);
                                                    await new Promise(r => setTimeout(r, 100)); 
                                                }
                                            }
                                        """)

                    selector = "//span[@data-testid='page-view-counter']"

                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        text_content = await page.locator(selector).inner_text()
                        match = re.search(r'\d+', text_content)
                        title_selector = await page.query_selector("//div[@data-testid='offer_title']/h4")

                        title_product = await title_selector.text_content()
                        if match:
                            views_count = int(match.group())
                            success = True
                            break  # Нашли данные, выходим из цикла попыток
                    except Exception:
                        logger.warning(f"Счетчик не найден на странице: {link.url}")
                        success = True  # Страница загрузилась, но счетчика нет (бывает)
                        break

                except Exception as e:
                    logger.error(f"Ошибка на попытке {attempt} для {link.url}: {e}")
                    await asyncio.sleep(5)

            if success:
                group.last_check = datetime.now(timezone.utc)
                await group.save()

                try:
                    async with in_transaction() as conn:
                        link.views = float(views_count)
                        link.last_check = datetime.now(timezone.utc)
                        link.productName = title_product
                        await link.save(using_db=conn)

                        await PriceHistory.create(
                            product_link=link,
                            views=views_count,
                            date=link.last_check,
                            using_db=conn
                        )
                    parsed_links += 1
                    data.append({
                        "Дата проверки": link.last_check.strftime("%d.%m.%Y"),
                        "Название продукта": title_product,
                        "Просмотры": views_count,
                        "Ссылка": link.url,
                    })
                except Exception as e:
                    logger.error(f"Ошибка записи в БД для {link.url}: {e}")

            progress_bar = format_progress(start_time, idx, total_links)
            new_text = f"🕵️‍♂️ Парсинг OLX (Просмотры): {group.title}\n{progress_bar}"

            if group.user.telegram_id:
                try:
                    if idx == 1:
                        msg = await bot.send_message(group.user.telegram_id, new_text)
                    else:
                        if msg and new_text != last_text:
                            await bot.edit_message_text(
                                chat_id=group.user.telegram_id,
                                message_id=msg.message_id,
                                text=new_text,
                            )
                            last_text = new_text
                except Exception as e:
                    logger.warning(f"Не удалось обновить прогресс: {e}")

        await browser.close()

    if data and group.user.telegram_id:
        excel_file = await generate_excel(data)

        await bot.send_document(
            chat_id=group.user.telegram_id,
            document=BufferedInputFile(excel_file.getvalue(), filename=f"OLX_Views_{group.title}.xlsx"),
            caption=(
                f"✅ Сбор просмотров завершён.\nВсего ссылок: {total_links}\nУспешно: {parsed_links}\n"
            )
        )


async def parse_satu_groups():
    """Запуск фонового парсера по всем активным группам."""
    logger.info("Запуск фонового парсера...")
    async with aiohttp.ClientSession() as session:
        parser = ProductParser(session)
        groups_satu = await ProductGroup.filter(is_active=True, site__title="SATU KZ").select_related(
            "user").prefetch_related("product_links")

        if not groups_satu:
            logger.info("Нет активных групп для парсинга")
            return

        for group in groups_satu:
            await process_group(group, parser)

    logger.info("Фоновый парсинг завершён ✅")


async def parse_olx_groups():
    """Запуск фонового парсера по всем активным группам."""
    logger.info("Запуск фонового парсера...")
    async with aiohttp.ClientSession() as session:
        parser = ProductParser(session)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)

        groups_olx = await ProductGroup.filter(
            is_active=True,
            site__title="OLX KZ",
            last_check__lte=seven_days_ago
        ).select_related("user").prefetch_related("product_links")

        if not groups_olx:
            logger.info("Нет активных групп для парсинга")
            return

        for group in groups_olx:
            await process_group(group, parser)

    logger.info("Фоновый парсинг завершён ✅")


async def parse_single_group(group_id: int):
    """Принудительный запуск парсинга только для одной группы."""
    group = await ProductGroup.get(id=group_id).select_related("user").prefetch_related("product_links", "site")
    site = group.site.title

    if not group:
        logger.warning(f"Группа с id={group_id} не найдена")
        return

    if site == 'SATU KZ':
        async with aiohttp.ClientSession() as session:
            parser = ProductParser(session)
            await process_group(group, parser)
    else:
        await process_olx_group(group)

    logger.info(f"Принудительный парсинг группы '{group.title}' (id={group.id}) завершён ✅")
