from tortoise import fields
from tortoise.models import Model


class ProductLink(Model):
    id = fields.IntField(pk = True)
    companyName = fields.CharField(max_length = 255, null = True)
    productName = fields.CharField(max_length = 255, null = True)
    url = fields.CharField(max_length = 500)
    last_price = fields.FloatField(null = True)
    last_check = fields.DatetimeField(null = True)

    group: fields.ForeignKeyRelation["ProductGroup"] = fields.ForeignKeyField(
        "models.ProductGroup", related_name = "product_links", on_delete = fields.CASCADE
    )

    price_history: fields.ReverseRelation["PriceHistory"]

    def __str__(self):
        return f"{self.companyName or ''} {self.productName}"

    class Meta:
        unique_together = ("url", "group")
