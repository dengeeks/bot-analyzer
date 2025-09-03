import io
import logging
from typing import Optional

import pandas as pd
from aiogram.types import BufferedInputFile
from openpyxl.styles import Alignment, Border, Side
from openpyxl.utils import get_column_letter

from bot.database.models.product_link import ProductLink

logger = logging.getLogger(__name__)


class TableHandler:
    """Класс для обработки операций с таблицами"""

    @staticmethod
    async def validate_and_read_file(file_bytes: io.BytesIO, file_name: str) -> Optional[pd.DataFrame]:
        """Валидация и чтение файла таблицы"""
        try:
            if file_name.endswith(".csv"):
                return pd.read_csv(file_bytes)
            elif file_name.endswith(".xlsx"):
                return pd.read_excel(file_bytes, engine = "openpyxl")
            return None
        except Exception as e:
            logger.error(f"Error reading file {file_name}: {e}")
            raise ValueError(f"Ошибка при чтении файла: {e}")

    @staticmethod
    def create_excel_with_autofit(links_data: list, group) -> BufferedInputFile:
        """Создание Excel файла с автоматической подгонкой ширины столбцов"""
        df = pd.DataFrame(links_data)

        thin_border = Border(
            left = Side(style = 'thin'),
            right = Side(style = 'thin'),
            top = Side(style = 'thin'),
            bottom = Side(style = 'thin')
        )

        with pd.ExcelWriter("temp.xlsx", engine = 'openpyxl') as writer:
            df.to_excel(writer, index = False)
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
                            cell_max_length = max(line_lengths, default = 0)
                            max_length = max(max_length, cell_max_length)

                            cell.alignment = Alignment(wrap_text = True)
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

        with open("temp.xlsx", "rb") as f:
            file_content = f.read()

        return BufferedInputFile(file_content, filename = f"{group.title}.xlsx")


class LinkService:
    @staticmethod
    async def delete_links_by_group(group_id: int) -> int:
        """Удаляет все ProductLink по group_id и возвращает количество удалённых ссылок."""
        deleted_count = await ProductLink.filter(group_id = group_id).delete()
        return deleted_count

    @staticmethod
    async def get_count_product_link_by_group_id(group_id: int):
        count = await ProductLink.filter(group_id = group_id).count()
        return count
