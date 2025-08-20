from bot.services.group import GroupService
from bot.services.link import LinkService


async def _get_group_info_text(group_id: int) -> str:
    """
    Генерирует стандартный текст информации о группе
    Устраняет дублирование кода в multiple handlers
    """
    group = await GroupService.get_group(group_id)
    count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

    parser_status_text = "⏸ Остановить парсер" if group.is_active else "▶️ Запустить парсер"

    return (
        f"ℹ️ Информация о группе:\n\n"
        f"Название: {group.title}\n"
        f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Статус: {'Активна ✅' if group.is_active else 'Неактивна ❌'}\n"
        f"Количество ссылок для анализа: {count_links}\n\n"

        "Доступные действия:\n"
        "📊 Просмотреть таблицу — посмотреть содержимое выбранной таблицы.\n"
        "📑 Просмотр последних результатов — увидеть итоговые данные последних парсеров.\n"
        "➕ Добавить таблицу — создать новую таблицу для данных.\n"
        "❌ Удалить таблицу — удалить ненужную таблицу.\n"
        f"{parser_status_text} — управление процессом парсинга по расписанию.\n"
        "⏭ Принудительный запуск — запустить парсер немедленно.\n"
        "📈 Получение анализа — получить аналитические данные по текущим таблицам.\n\n"
        "Выберите действие, которое хотите выполнить, используя кнопки ниже ⬇️"
    )
