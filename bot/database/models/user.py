from tortoise import fields
from tortoise.models import Model


class User(Model):
    id = fields.IntField(pk = True)
    telegram_id = fields.BigIntField(unique = True)
    name = fields.CharField(max_length = 100)
    username = fields.CharField(max_length = 235, null = True)

    def __str__(self) -> str:
        return self.name
