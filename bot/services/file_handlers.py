import io
import logging
from abc import ABC, abstractmethod

import pandas as pd
from pandas import DataFrame

logger = logging.getLogger(__name__)


class FileHandlerStrategy(ABC):
    """Абстрактный класс стратегии для обработки файлов"""

    @abstractmethod
    async def validate_and_read(self, file_bytes: io.BytesIO) -> DataFrame:
        pass

    @abstractmethod
    def get_supported_extensions(self) -> list[str]:
        """Возвращает список поддерживаемых расширений"""
        pass


class ExcelFileHandler(FileHandlerStrategy):
    """Обработчик Excel файлов"""

    async def validate_and_read(self, file_bytes: io.BytesIO) -> DataFrame:
        try:
            file_bytes.seek(0)
            return pd.read_excel(file_bytes)
        except Exception as e:
            logger.error(f"Ошибка чтения Excel файла: {e}")
            raise ValueError("Невозможно прочитать Excel файл. Проверьте формат.")

    def get_supported_extensions(self) -> list[str]:
        return ['.xlsx', '.xls']


class CSVFileHandler(FileHandlerStrategy):
    """Обработчик CSV файлов"""

    async def validate_and_read(self, file_bytes: io.BytesIO) -> DataFrame:
        try:
            file_bytes.seek(0)
            content = file_bytes.read().decode('utf-8')
            return pd.read_csv(io.StringIO(content))
        except UnicodeDecodeError:
            # Попробуем другие кодировки
            try:
                file_bytes.seek(0)
                content = file_bytes.read().decode('cp1251')
                return pd.read_csv(io.StringIO(content))
            except Exception as e:
                logger.error(f"Ошибка чтения CSV файла: {e}")
                raise ValueError("Невозможно прочитать CSV файл. Проверьте кодировку.")
        except Exception as e:
            logger.error(f"Ошибка чтения CSV файла: {e}")
            raise ValueError("Невозможно прочитать CSV файл. Проверьте формат.")

    def get_supported_extensions(self) -> list[str]:
        return ['.csv']


class FileHandlerFactory:
    """Фабрика для создания обработчиков файлов"""

    _handlers: dict[str, FileHandlerStrategy] = {}

    @classmethod
    def register_handler(cls, extension: str, handler: FileHandlerStrategy) -> None:
        """Регистрирует обработчик для расширения"""
        cls._handlers[extension.lower()] = handler

    @classmethod
    def create_handler(cls, filename: str) -> FileHandlerStrategy:
        """Создает обработчик на основе расширения файла"""
        if not filename:
            raise ValueError("Имя файла не может быть пустым")

        # Извлекаем расширение файла
        if '.' not in filename:
            raise ValueError(f"Файл '{filename}' не имеет расширения")

        extension = filename[filename.rfind('.'):].lower()

        if extension in cls._handlers:
            return cls._handlers[extension]

        # Автоматическая регистрация стандартных обработчиков при первом вызове
        if not cls._handlers:
            cls._register_default_handlers()
            if extension in cls._handlers:
                return cls._handlers[extension]

        supported_extensions = list(cls._handlers.keys())
        raise ValueError(
            f"Неподдерживаемый формат файла: {extension}. "
            f"Поддерживаемые форматы: {', '.join(supported_extensions)}"
        )

    @classmethod
    def _register_default_handlers(cls) -> None:
        """Регистрирует стандартные обработчики"""
        cls.register_handler('.xlsx', ExcelFileHandler())
        cls.register_handler('.xls', ExcelFileHandler())
        cls.register_handler('.csv', CSVFileHandler())

    @classmethod
    def get_supported_extensions(cls) -> list[str]:
        """Возвращает список поддерживаемых расширений"""
        if not cls._handlers:
            cls._register_default_handlers()
        return list(cls._handlers.keys())


class FileProcessor:
    """Универсальный процессор файлов с обработкой ошибок"""

    REQUIRED_COLUMNS = ['Ссылка на товар']

    @staticmethod
    async def process_file(file_bytes: io.BytesIO, filename: str) -> DataFrame:
        """
        Обрабатывает файл и возвращает DataFrame с валидацией бизнес-правил
        """
        try:
            # Создаем обработчик и читаем файл
            handler = FileHandlerFactory.create_handler(filename)
            df = await handler.validate_and_read(file_bytes)

            # Базовая валидация данных
            if df.empty:
                raise ValueError("Файл не содержит данных")

            # Валидация обязательных колонок (бизнес-правило)
            missing_columns = [
                col for col in FileProcessor.REQUIRED_COLUMNS
                if col not in df.columns
            ]

            if missing_columns:
                raise ValueError(
                    f"В таблице отсутствуют обязательные колонки: {', '.join(missing_columns)}"
                )

            # Дополнительная валидация URL (опционально)
            if 'Ссылка на товар' in df.columns:
                invalid_urls = df[~df['Ссылка на товар'].str.startswith('https://satu.kz/', na = False)]
                if not invalid_urls.empty:
                    logger.warning(f"Найдено {len(invalid_urls)} ссылок не с satu.kz")

            return df

        except ValueError as e:
            # Перебрасываем известные ошибки валидации
            logger.warning(f"Ошибка валидации файла {filename}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Неожиданная ошибка при обработке файла {filename}: {e}")
            raise ValueError(f"Ошибка обработки файла: {str(e)}")
