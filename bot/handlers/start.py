from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.filters.admin import AdminFilter
from bot.keyboards.site import get_sites_keyboard
from bot.keyboards.start import main_start_keyboard
from bot.services.site import SiteService
from bot.services.user import UserService
from core.config import load_config

config = load_config()
admin_ids = config.tg_bot.admin_ids

router = Router()
router.message.filter(AdminFilter(admin_ids))


@router.message(F.text == "/start")
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Создаёт пользователя в БД (если его нет) и показывает главное меню.
    """

    # получение данных пользователя
    telegram_id = message.from_user.id
    name = message.from_user.full_name
    username = message.from_user.username

    # получение или создание пользователя
    await UserService.get_or_create_user(
        telegram_id = telegram_id,
        name = name,
        username = username,
    )

    text = (
        f"👋 Привет, {message.from_user.full_name}!\n\n"
        "Я бот-парсер 📊\n\n"
        "⚡ Каждый день я:\n"
        "• Анализирую конкурентов\n"
        "• Отслеживаю изменения цен на их товары\n"
        "• Помогаю тебе быть в курсе рынка\n\n"
    )

    await message.answer(text, reply_markup = main_start_keyboard())


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    """
    Обработчик кнопки "Назад".
    Возвращает пользователя в главное меню.
    """

    # Закрываем текущие состояния, если были
    await callback.bot.delete_message(callback.from_user.id, callback.message.message_id)

    # Вызываем /start заново
    telegram_id = callback.from_user.id
    name = callback.from_user.full_name
    username = callback.from_user.username

    # получение или создание пользователя
    await UserService.get_or_create_user(
        telegram_id = telegram_id,
        name = name,
        username = username,
    )

    text = (
        f"👋 Привет, {callback.from_user.full_name}!\n\n"
        "Я бот-парсер 📊\n\n"
        "⚡ Каждый день я:\n"
        "• Анализирую конкурентов\n"
        "• Отслеживаю изменения цен на их товары\n"
        "• Помогаю тебе быть в курсе рынка\n\n"
    )

    await callback.message.answer(text, reply_markup = main_start_keyboard())
    await callback.answer()


# Главное меню → список сайтов
@router.callback_query(F.data == "menu_sites")
async def show_sites(callback: CallbackQuery):
    """
    Главное меню → список сайтов.
    Показывает все сайты из БД с кнопками.
    """

    # получение всех сайтов
    sites = await SiteService.get_sites()
    if not sites:
        await callback.message.edit_text("❌ Пока нет сайтов в базе.", reply_markup = get_sites_keyboard(sites))
    else:
        await callback.message.edit_text("📂 Сайты:", reply_markup = get_sites_keyboard(sites))
    await callback.answer()
