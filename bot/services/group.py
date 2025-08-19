from typing import Optional

from bot.database.models.product_group import ProductGroup
from bot.database.models.site import Site
from bot.database.models.user import User


class GroupHandler:
    """Класс для обработки операций с группами"""

    @staticmethod
    async def get_group_info_text(group) -> str:
        """Генерация текста с информацией о группе"""
        return (
            f"Информация о группе:\n\n"
            f"Название: {group.title}\n"
            f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"Активна: {'Да' if group.is_active else 'Нет'}\n\n"
            f"<b>ПРИ ДОБАВЛЕНИИ ТАБЛИЦЫ, УБЕДИТЕСЬ ЧТО ВСЕ ССЫЛКИ ЯВЛЯЮТСЯ satu.kz..</b>"
        )

    @staticmethod
    async def validate_group_title(title: str) -> Optional[str]:
        """Валидация названия группы"""
        title = title.strip()
        if not title:
            return "❌ Название группы не может быть пустым. Попробуйте ещё раз."
        if len(title) > 100:
            return "❌ Название группы слишком длинное (макс. 100 символов)."
        return None


class GroupService:

    @staticmethod
    async def update_parser_status(group_id: int, is_active: bool) -> None:
        """Обновляет статус парсера для группы"""
        group = await ProductGroup.get_or_none(id = group_id)
        if group:
            group.is_active = is_active
            await group.save()

        return group

    @staticmethod
    async def delete_group(group_id: int):
        """
        Удаляет группу по её ID.
        Возвращает количество удалённых записей (0 или 1).
        """
        return await ProductGroup.filter(id = group_id).delete()

    @staticmethod
    async def get_groups(site_id: int, user_telegram_id: int) -> list[ProductGroup]:
        """
        Возвращает список групп по site_id и telegram_id пользователя.
        """
        user = await User.get(telegram_id = user_telegram_id)

        return await ProductGroup.filter(
            site_id = site_id,
            user = user
        )

    @staticmethod
    async def get_group(group_id: int) -> ProductGroup:
        """
        Получает одну группу по её ID.
        Бросает исключение DoesNotExist, если группа не найдена.
        """
        return await ProductGroup.get(id = group_id)

    @staticmethod
    async def add_group(site_id: int, title: str, telegram_id: int) -> ProductGroup:
        """
        Создаёт новую группу товаров.

        Аргументы:
            site_id: ID сайта, к которому привязана группа.
            title: Название группы.
            telegram_id: Telegram ID пользователя, которому принадлежит группа.

        Возвращает:
            Объект ProductGroup.
        """

        # Берем сайт
        site = await Site.get(id = site_id)

        # Берем пользователя по telegram_id
        user = await User.get(telegram_id = telegram_id)

        # Создаем группу
        return await ProductGroup.create(
            site = site,
            user = user,
            title = title
        )
