import io
import logging
from typing import Any, Optional

import pandas as pd
from aiogram.types import Message
from openpyxl.utils import get_column_letter

from bot.database.models.price_history import PriceHistory
from bot.database.models.product_link import ProductLink
from bot.keyboards.group import group_detail_keyboard
from bot.services.group import GroupService
from bot.tasks.parse import generate_excel

logger = logging.getLogger(__name__)


async def _process_links(urls: pd.Series, group_id: int, site_title: str) -> int:
    """Обработка и сохранение списка ссылок"""
    created_count = 0
    for url in urls.dropna().unique():
        url = str(url).strip()
        if not url:
            continue

        if site_title == "SATU KZ":
            # Валидация: проверяем, что ссылка начинается с https://satu.kz
            if not url.startswith('https://satu.kz'):
                logger.warning(f"Пропущена ссылка {url}: должна начинаться с https://satu.kz")
                continue
        else:
            # Валидация: проверяем, что ссылка начинается с https://satu.kz
            if not url.startswith('https://www.olx.kz'):
                logger.warning(f"Пропущена ссылка {url}: должна начинаться с https://www.olx.kz")
                continue

        try:
            await ProductLink.create(
                group_id=group_id,
                url=url,
                companyName=None,
                productName=None,
                last_price=None,
                last_check=None
            )
            created_count += 1
        except Exception as e:
            logger.warning(f"Ошибка при добавлении ссылки в базу {url}: {e}")

    return created_count


async def _send_group_info(
        message: Message,
        group_id: int,
        site_id: int,
        additional_text: str = ""
) -> None:
    """Отправка информации о группе"""
    group = await GroupService.get_group(group_id)
    text = (
        f"Информация о группе:\n\n"
        f"Название: {group.title}\n"
        f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Активна: {'Да' if group.is_active else 'Нет'}\n\n"
        f"{additional_text}\n\n"
        "Вы можете продолжить работу с группой:"
    )
    await message.answer(
        text,
        reply_markup=group_detail_keyboard(group_id, site_id, group.is_active)
    )


def _generate_group_info_text(group: Any, links_count: Optional[int] = None) -> str:
    """Генерация текста с информацией о группе"""
    base_text = (
        f"Информация о группе:\n\n"
        f"Название: {group.title}\n"
        f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Активна: {'Да' if group.is_active else 'Нет'}\n\n"
    )

    if links_count is not None:
        base_text += f"Количество ссылок для анализа: {links_count}.\n\n"

    return base_text


async def generate_last_views_diff_excel(group_id: int) -> io.BytesIO:
    """
    Сравнивает только ПОСЛЕДНИЙ и ПРЕДПОСЛЕДНИЙ парсинг.
    Показывает прирост просмотров за этот период.
    """
    links = await ProductLink.filter(group_id=group_id).all()
    if not links:
        return None

    data_rows = []

    for link in links:
        last_records = await PriceHistory.filter(product_link=link).order_by('-date').limit(2)

        if not last_records:
            continue

        current_rec = last_records[0]
        current_views = current_rec.views if current_rec.views is not None else 0

        if len(last_records) == 2:
            prev_rec = last_records[1]
            prev_views = prev_rec.views if prev_rec.views is not None else 0

            diff = current_views - prev_views

            if diff > 0:
                sign = f"➕{diff}"
            elif diff < 0:
                sign = f"➖{abs(diff)}"
            else:
                sign = "0"

            prev_date_str = prev_rec.date.strftime("%d.%m %H:%M")
        else:
            prev_views = 0
            sign = "🆕 Новый"
            prev_date_str = "-"

        # Формируем строку для отчета
        data_rows.append({
            "Название продукта": link.productName,
            "Ссылка": link.url,
            "Всего просмотров": current_views,
            "Прирост": sign,
            "Было (дата)": f"{prev_views} ({prev_date_str})",
            "Дата проверки": current_rec.date.strftime("%d.%m.%Y %H:%M")

        })

    if not data_rows:
        return None

    output = await generate_excel(data_rows)
    return output


async def generate_price_diff_excel(group_id: int) -> io.BytesIO:
    """
    Генерация Excel с анализом разницы между последней и предпоследней ценой
    для всех ссылок в группе.
    """
    links = await ProductLink.filter(group_id=group_id).all()
    if not links:
        return None

    data_rows = []
    for link in links:
        # Берём последние две цены
        price_objs = await PriceHistory.filter(product_link=link).order_by('-date').limit(2)

        if len(price_objs) < 2:
            # Мало данных для сравнения
            data_rows.append(
                {
                    "Компания": link.companyName or "",
                    "Товар": link.productName or "",
                    "Последняя цена": price_objs[0].price if price_objs else None,
                    "Предыдущая цена": None,
                    "Разница": None,
                    "%": None,
                    "Символ": "ℹ️ Данных недостаточно",
                    "Ссылка": link.url
                }
            )
            continue

        last_price = price_objs[0]
        prev_price = price_objs[1]

        diff = last_price.price - prev_price.price
        percent = (diff / prev_price.price * 100) if prev_price.price else 0
        sign = "🔺" if diff > 0 else ("🔻" if diff < 0 else "➖")

        data_rows.append(
            {
                "Компания": link.companyName or "",
                "Товар": link.productName or "",
                "Предыдущая цена": prev_price.price,
                "Последняя цена": last_price.price,
                "Разница": diff,
                "%": percent,
                "Символ": sign,
                "Ссылка": link.url
            }
        )

    if not data_rows:
        return None

    df = pd.DataFrame(data_rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Анализ цен")
        worksheet = writer.sheets["Анализ цен"]

        # Автоширина колонок
        for col in worksheet.columns:
            max_length = max((len(str(cell.value)) for cell in col), default=10)
            worksheet.column_dimensions[get_column_letter(col[0].column)].width = (max_length + 2) * 1.2

    output.seek(0)
    return output
