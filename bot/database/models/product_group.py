from tortoise import fields
from tortoise.models import Model


class ProductGroup(Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)

    site: fields.ForeignKeyRelation["Site"] = fields.ForeignKeyField(
        "models.Site", related_name="product_groups", on_delete=fields.CASCADE
    )
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="product_groups",
        on_delete=fields.CASCADE
    )
    is_active = fields.BooleanField(default=False)
    last_check = fields.DatetimeField(null = True)

    product_links: fields.ReverseRelation["ProductLink"]

    def __str__(self):
        return self.title
