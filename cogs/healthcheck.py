import asyncio
from aiohttp import web
from discord.ext import commands

class Healthcheck(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.runner = None
        self.bot.loop.create_task(self.start_health_server())

    async def start_health_server(self):
        async def handle_health(request):
            return web.Response(text="OK")

        app = web.Application()
        app.router.add_get("/health", handle_health)

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, host="0.0.0.0", port=3838)
        await site.start()
        print("[healthcheck] Server started on port 3838")

    async def cog_unload(self):
        """Clean up the health check server when cog is unloaded."""
        if self.runner:
            try:
                await self.runner.cleanup()
                print("[healthcheck] Health check server stopped")
            except Exception as e:
                print(f"[healthcheck] Error during cleanup: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Healthcheck(bot))
