from tortoise import fields
from tortoise.models import Model


class Site(Model):
    id = fields.IntField(pk = True)
    title = fields.CharField(max_length = 255, unique = True)
    created_at = fields.DatetimeField(auto_now_add = True)

    product_groups: fields.ReverseRelation["ProductGroup"]

    def __str__(self):
        return self.title
