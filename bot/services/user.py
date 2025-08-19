from bot.database.models.user import User


class UserService:
    @staticmethod
    async def get_or_create_user(telegram_id: int, name: str, username: str | None = None) -> tuple[User, bool]:
        """
        Возвращает пользователя, если он есть, иначе создаёт нового.
        :return: (user, created)
        """
        return await User.get_or_create(
            telegram_id=telegram_id,
            defaults={"name": name, "username": username},
        )