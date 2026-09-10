from discord.ext import commands


class CommandBase(commands.Cog):
    def __init__(self, bot):
        self.bot, self.app = bot, bot.app

    async def defer(self, i):
        await i.response.defer(ephemeral=True)
