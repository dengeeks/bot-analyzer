import asyncio
import io
import logging
from typing import Dict

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, BufferedInputFile

from bot.database.models.price_history import PriceHistory
from bot.database.models.product_link import ProductLink
from bot.filters.admin import AdminFilter
from bot.fsm.link import TableStates
from bot.keyboards.group import group_detail_keyboard
from bot.keyboards.link import confirm_delete_group_links_keyboard
from bot.services.file_handlers import FileProcessor
from bot.services.group import GroupService
from bot.services.link import LinkService, TableHandler
from bot.tasks.parse import parse_single_group
from bot.utils.callback import parse_callback
from bot.utils.group import _get_group_info_text, _get_add_table_info_text
from bot.utils.link import _process_links, generate_price_diff_excel, generate_total_views_diff_excel
from core.config import load_config

logger = logging.getLogger(__name__)

config = load_config()
admin_ids = config.tg_bot.admin_ids

router = Router()
router.message.filter(AdminFilter(admin_ids))
running_tasks: Dict[int, asyncio.Task] = {}


async def _update_parser_status_and_respond(
        callback: CallbackQuery,
        group_id: int,
        site_id: int,
        is_active: bool,
        success_message: str
) -> None:
    """Общая функция для обновления статуса парсера и ответа"""
    await GroupService.update_parser_status(group_id, is_active=is_active)
    group = await GroupService.get_group(group_id)
    group_info_text = await _get_group_info_text(group_id)

    await callback.answer(success_message)
    await callback.message.edit_text(
        text=group_info_text,
        reply_markup=group_detail_keyboard(
            group_id=group_id,
            site_id=site_id,
            is_parser_active=group.is_active
        )
    )


def _prepare_links_data(links, is_final: bool = False) -> list:
    """Подготавливает данные ссылок для Excel"""
    if is_final:
        return [{
            "Название товара": link.productName or "N/A",
            "Название компании": link.companyName or "N/A",
            "Стоимость": link.last_price or "N/A",
            "Ссылка": link.url,
            "Дата последней проверки": link.last_check.strftime("%d.%m.%Y") if link.last_check else "N/A"
        } for link in links]
    else:
        return [{
            "Название продукта": link.productName,
            "Название компании": link.companyName,
            "Ссылка на товар": link.url
        } for link in links]


async def _prepare_olx_links_data(links) -> list:
    """Подготавливает данные ссылок для Excel"""
    result = []

    for link in links:
        last_history = await PriceHistory.filter(product_link_id=link.id).order_by("-date").first()
        current_views = last_history.views if last_history is not None else 0
        result.append({
            "Название продукта": link.productName,
            "Ссылка на товар": link.url,
            "Кол-во просмотров": current_views,
            "Дата последней проверки": link.last_check.strftime("%d.%m.%Y") if link.last_check else "N/A"
        }
        )
    return result


@router.callback_query(F.data.startswith("add_table_"))
async def add_table_start(callback: CallbackQuery, state: FSMContext):
    """Обработчик начала загрузки таблицы"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)

        await state.update_data(group_id=int(group_id), site_id=int(site_id))
        await state.set_state(TableStates.uploading_table)

        # Генерация ответа
        group = await GroupService.get_group(group_id)
        add_table_info_text = await _get_add_table_info_text(group)

        await callback.message.answer(add_table_info_text)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в add_table_start: {e}")
        await callback.message.answer("❌ Произошла ошибка при обработке запроса")
        await callback.answer("Ошибка обработки запроса")


@router.message(TableStates.uploading_table, F.document)
async def upload_table(message: Message, state: FSMContext):
    """Обработка загруженной таблицы"""
    try:
        data = await state.get_data()
        group_id = data["group_id"]
        site_id = data["site_id"]

        group = await GroupService.get_group(group_id)
        await group.fetch_related("site")
        site_title = group.site.title

        # Скачивание файла
        file_bytes = io.BytesIO()
        await message.bot.download(message.document.file_id, destination=file_bytes)

        # Валидация и чтение файла
        df = await FileProcessor.process_file(file_bytes, message.document.file_name, site_title)

        # Обработка ссылок
        created_count = await _process_links(df["Ссылка на товар"], group_id, site_title)

        # Генерация ответа
        group_info_text = await _get_group_info_text(group_id)
        group = await GroupService.get_group(group_id)

        await message.answer(f'✅ Успешно добавлено {created_count} ссылок')
        await message.answer(
            group_info_text,
            reply_markup=group_detail_keyboard(group_id, site_id, group.is_active),
        )

    except ValueError as e:
        logger.warning(f"Ошибка валидации файла: {e}")
        await message.answer(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Критическая ошибка при обработке таблицы: {e}")
        await message.answer("❌ Произошла непредвиденная ошибка при обработке файла")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("view_table_"))
async def view_table_handler(callback: CallbackQuery):
    """Генерация и отправка таблицы со ссылками"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)

        group = await GroupService.get_group(group_id)
        links = await ProductLink.filter(group_id=group_id).all()

        if not links:
            await callback.answer("ℹ️ В этой группе пока нет ссылок для анализа.")
            return

        # Подготовка данных для Excel
        links_data = _prepare_links_data(links, is_final=False)
        excel_file = TableHandler.create_excel_with_autofit(links_data, group)
        group_info_text = await _get_group_info_text(group_id)

        await callback.message.answer_document(excel_file, caption='Входная таблица')
        await callback.message.answer(
            group_info_text,
            reply_markup=group_detail_keyboard(group.id, site_id, group.is_active)
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в view_table_handler: {e}")
        await callback.answer("❌ Ошибка при генерации таблицы")


@router.callback_query(F.data.startswith("delete_table_"))
async def delete_links(callback: CallbackQuery):
    """Подтверждение удаления ссылок группы"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)

        group = await GroupService.get_group(group_id)
        links_count = await ProductLink.filter(group_id=group_id).count()

        if not links_count:
            await callback.answer("ℹ️ В этой группе пока нет ссылок для удаления.")
            return

        confirmation_text = (
            f"<b>Информация о группе</b>:\n"
            f"Название: {group.title}\n"
            f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"Активна: {'Да' if group.is_active else 'Нет'}\n\n"
            f"<b>Информация о таблице</b>: \n"
            f"Количество ссылок: {links_count} \n\n"
            f"<b>Вы уверены, что хотите удалить все ссылки этой группы?</b>"
        )

        await callback.message.edit_text(
            confirmation_text,
            reply_markup=confirm_delete_group_links_keyboard(group_id, site_id)
        )

    except Exception as e:
        logger.error(f"Ошибка в delete_links: {e}")
        await callback.answer("❌ Ошибка при обработке запроса")


@router.callback_query(F.data.startswith(("links_confirm_", "links_cancel_")))
async def process_delete_links_confirmation(callback: CallbackQuery):
    """Обработка подтверждения удаления ссылок"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)
        group = await GroupService.get_group(group_id)

        if callback.data.startswith("links_confirm_"):
            deleted_count = await LinkService.delete_links_by_group(group_id)
            await callback.answer(f"✅ Удалено {deleted_count} ссылок!")
        else:
            await callback.answer("❌ Удаление отменено.")

        group_info_text = await _get_group_info_text(group_id)

        await callback.message.edit_text(
            group_info_text,
            reply_markup=group_detail_keyboard(group_id, site_id, group.is_active)
        )

    except Exception as e:
        logger.error(f"Ошибка в process_delete_links_confirmation: {e}")
        await callback.answer("❌ Ошибка при обработке подтверждения")


@router.callback_query(F.data.startswith("start_parser_"))
async def start_parser_handler(callback: CallbackQuery):
    """Обработчик запуска парсера для группы"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)
        await _update_parser_status_and_respond(
            callback, group_id, site_id, True, "✅ Парсер успешно запущен!"
        )
    except Exception as e:
        logger.error(f"Ошибка в start_parser_handler: {e}")
        await callback.answer("❌ Ошибка при запуске парсера")


@router.callback_query(F.data.startswith("stop_parser_"))
async def stop_parser_handler(callback: CallbackQuery):
    """Обработчик остановки парсера для группы"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)
        await _update_parser_status_and_respond(
            callback, group_id, site_id, False, "⏹ Парсер остановлен!"
        )
    except Exception as e:
        logger.error(f"Ошибка в stop_parser_handler: {e}")
        await callback.answer("❌ Ошибка при остановке парсера")


@router.callback_query(F.data.startswith("force_start_"))
async def force_start_parser(callback: CallbackQuery):
    """Принудительный запуск парсера"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)

        if running_tasks.get(group_id):
            await callback.answer("⚠️ Парсер уже запущен для этой группы")
            return

        links_count = await ProductLink.filter(group_id=group_id).count()

        if not links_count:
            await callback.answer("❌ В базе отсутствуют ссылки для парсинга.")
            return

        await callback.answer("⏳ Запускаю парсер...")

        # Запускаем парсер
        task = asyncio.create_task(parse_single_group(group_id))
        running_tasks[group_id] = task

        # Очистка задачи после завершения
        def cleanup_task(future):
            running_tasks.pop(group_id, None)

        task.add_done_callback(cleanup_task)

    except Exception as e:
        logger.error(f"Ошибка в force_start_parser: {e}")
        await callback.answer("❌ Ошибка при запуске парсера")


@router.callback_query(F.data.startswith("final_table_"))
async def view_final_table(callback: CallbackQuery):
    """Генерация и отправка финальной таблицы с результатами"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)

        group = await GroupService.get_group(group_id)
        await group.fetch_related('site')
        site = group.site

        links = await ProductLink.filter(group_id=group_id).all()
        if not links:
            await callback.answer("❌ В этой группе пока нет ссылок.")
            return

        if site.title == 'SATU KZ':
            # Проверка наличия цен
            has_prices = any(link.last_price is not None for link in links)
            if not has_prices:
                await callback.answer("❌ Парсинг ещё не был выполнен.")
                return

        # Подготовка данных
        if site.title == 'SATU KZ':
            links_data = _prepare_links_data(links, is_final=True)
        else:
            links_data = await _prepare_olx_links_data(links)

        excel_file = TableHandler.create_excel_with_autofit(links_data, group)
        group_info_text = await _get_group_info_text(group_id)

        await callback.message.answer_document(excel_file, caption="Выходная таблица с данными")
        await callback.message.answer(
            group_info_text,
            reply_markup=group_detail_keyboard(group.id, site_id, group.is_active)
        )

    except Exception as e:
        logger.error(f"Ошибка в view_final_table: {e}")
        await callback.answer("❌ Ошибка при генерации таблицы")


@router.callback_query(F.data.startswith("price_analysis_"))
async def price_analysis(callback: CallbackQuery):
    """Анализ цен и генерация отчета"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)

        group = await GroupService.get_group(group_id)
        await group.fetch_related('site')
        site = group.site

        if site == 'SATU KZ':
            excel_file = await generate_price_diff_excel(group_id)
            if not excel_file:
                await callback.answer("❌ Нет данных для анализа цен")
                return
        else:
            excel_file = await generate_total_views_diff_excel(group_id)

            if not excel_file:
                await callback.answer("❌ Нет данных для анализа просмотров")
                return

        group_info_text = await _get_group_info_text(group_id)

        if site == 'SATU KZ':
            await callback.message.answer_document(
                document=BufferedInputFile(
                    excel_file.getvalue(),
                    filename=f"Анализ_группы_{group.title}.xlsx"
                ),
                caption=f"📊 Анализ цен группы {group.title}"
            )
        else:
            await callback.message.answer_document(
                document=BufferedInputFile(
                    excel_file.getvalue(),
                    filename=f"Анализ_группы_{group.title}.xlsx"
                ),
                caption=f"📊 Анализ просмотров группы {group.title}"
            )

        await callback.message.answer(
            text=group_info_text,
            reply_markup=group_detail_keyboard(
                group_id=group_id,
                site_id=site_id,
                is_parser_active=group.is_active
            )
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в price_analysis: {e}")
        await callback.answer("❌ Ошибка при анализе цен")
