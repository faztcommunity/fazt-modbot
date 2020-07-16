from discord import Color, Embed
from discord.ext import commands

from .. import crud
from ..config import Settings
from ..utils import to_str_bool


# TODO Put the help and aliases in the commands here
class BotConfigCmds(commands.Cog, name='Configuraciones del bot (para developers)'):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_check(self, ctx: commands.Context):
        return ctx.author.id in Settings.DEVELOPERS_ID

    @commands.command()
    async def debug(self, ctx: commands.Context, value: bool):
        crud.set_guild_setting(ctx.guild.id, 'debug', to_str_bool(value))
        embed = Embed(
            title='Debug editado! ✅',
            description=f'Debug ha sido puesto como `{value}`',
            color=Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command(help='Recarga el bot', usage='[extención]')
    async def reload(self, ctx: commands.Context, *args: str):
        if ctx.author.id not in Settings.DEVELOPERS_ID:
            raise commands.MissingPermissions

        if args:
            for arg in args:
                self.bot.reload_extension(arg)
        else:
            self.bot.reload_extension('bot.cogs')
            self.bot.reload_extension('bot.commands')

        embed = Embed(
            title='Reloaded ✅',
            color=Color.red(),
            description='Bot recargado satisfactoriamente!'
        )

        await ctx.send(embed=embed)
