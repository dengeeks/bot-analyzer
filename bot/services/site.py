from bot.database.models.site import Site


class SiteService:
    @staticmethod
    async def get_sites():
        return await Site.all()

    @staticmethod
    async def get_site(site_id: int) -> Site:
        return await Site.get_or_none(id = site_id)
