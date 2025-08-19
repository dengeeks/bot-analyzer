from tortoise import fields
from tortoise.models import Model


class PriceHistory(Model):
    id = fields.IntField(pk=True)
    price = fields.IntField()
    date = fields.DatetimeField()

    product_link: fields.ForeignKeyRelation["ProductLink"] = fields.ForeignKeyField(
        "models.ProductLink", related_name="price_history", on_delete=fields.CASCADE
    )

    def __str__(self):
        return f"{self.price} в {self.date}"
