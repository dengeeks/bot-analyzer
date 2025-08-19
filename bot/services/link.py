import io
import logging
from typing import Optional

import pandas as pd
from aiogram.types import BufferedInputFile
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

        with pd.ExcelWriter("temp.xlsx", engine = 'openpyxl') as writer:
            df.to_excel(writer, index = False)
            workbook = writer.book
            worksheet = writer.sheets['Sheet1']

            for column in worksheet.columns:
                max_length = max(
                    (len(str(cell.value)) for cell in column),
                    default = 10
                )
                adjusted_width = (max_length + 2) * 1.2
                column_letter = get_column_letter(column[0].column)
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
