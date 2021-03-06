"""
Copyright 2020 Fazt Community ~ All rights reserved. MIT license.
"""

from asyncio import create_task
from datetime import datetime, timedelta
from typing import Callable, Optional

from discord import (
    Color,
    Embed,
    Forbidden,
    Member,
    Message,
    PermissionOverwrite,
    Role,
    utils,
)
from discord.ext.commands import Bot, Cog, Context, Greedy, command, has_permissions

from .. import crud
from ..enums import GuildSetting, ModerationType
from ..utils import Confirm, Duration, MentionedMember
from ..utils import callback as cb
from ..utils import delete_message, get_role, get_value
from ..utils import unmoderate as unmod

no_logs_channel_msg = (
    "Usuario {title}. Considere agregar un canal para los logs usando `{prefix}set channel "
    "moderation #canal`. Este mensaje se eliminara en 10 segundos."
)

usage = "<usuarios> [duración] <razón>` Ejemplo de la duración: `1d5h3m10s` (1 dia, 5 horas, 3 minutos y 10 segundos)`"
usage2 = "<usuarios> <razón>"


async def unmoderate(ctx, moderation_type, member, after_duration, expiration_date):
    if expiration_date:
        await utils.sleep_until(expiration_date)
        await unmod(after_duration, member.id, ctx.guild.id, moderation_type)


class ModerationCmds(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    def cog_check(self, ctx: Context):
        role = get_role(ctx.guild, GuildSetting.MIN_MOD_ROLE)
        if role is None:
            # TODO !!!!
            create_task(
                ctx.send(
                    "Por favor configura el mínimo rol requerido para usar los comandos de moderación: "
                    f"`{ctx.prefix}set role minmod @Rol`."
                )
            )
            return False
        return ctx.author.top_role and ctx.author.top_role >= role

    async def moderate(
        self,
        ctx: Context,
        callback: Callable,
        moderation_type: ModerationType,
        reason: str,
        member: Member,
        emoji: str = "",
        duration: Optional[int] = None,
        after_duration: Callable = None,
    ):
        await delete_message(ctx.message)

        if member.top_role and not ctx.author.top_role > member.top_role:
            return await ctx.send(
                f"No puedes moderar a {member.display_name}.", delete_after=10
            )

        moderation_date = datetime.utcnow()

        expiration_date = None
        if duration and after_duration:
            expiration_date = moderation_date + timedelta(minutes=duration)

        value = get_value(reason, duration, expiration_date)

        title = moderation_type.value
        try:
            await member.send(
                f"Has sido {title} en {ctx.guild.name}. Recuerda seguir las reglas!"
                + value
            )
        except Forbidden:
            await ctx.send(
                f"El usuario {member.display_name} tiene bloqueados los mensajes directos",
                delete_after=10,
            )

        await callback(reason=reason)
        crud.moderate(
            moderation_type,
            member.id,
            moderation_date,
            expiration_date,
            ctx.guild.id,
            ctx.author.id,
            reason or "",
        )

        guild = crud.get_guild(member.guild.id)
        channel = crud.get_set_channel(self.bot, guild, GuildSetting.MODERATION_CHANNEL)

        if channel:
            embed = Embed(
                title=f"{emoji} Usuario {title}: {member.display_name}",
                description=f"El usuario {member.mention} ha sido {title} por {ctx.author.mention}\n"
                + value,
                color=Color.red(),
            )

            if expiration_date:
                embed.timestamp = expiration_date
                embed.set_footer(text="Expira:")

            message = member.mention

            if moderation_type == ModerationType.WARN:
                warning_role: Role = get_role(ctx.guild, GuildSetting.WARNING_ROLE)

                message += f" {warning_role.mention}"

            rules_channel = crud.get_set_channel(
                self.bot, guild, GuildSetting.RULES_CHANNEL
            )

            if rules_channel:
                message += " lee las reglas: " + rules_channel.mention

            await channel.send(message, embed=embed)

        else:
            await ctx.send(
                no_logs_channel_msg.format(title=title, prefix=ctx.prefix),
                delete_after=10,
            )

        create_task(
            unmoderate(ctx, moderation_type, member, after_duration, expiration_date)
        )

    @command(help="Advierte a un usuario.", usage=usage2)
    async def warn(
        self, ctx: Context, members: Greedy[MentionedMember], *, reason: str
    ):
        role = get_role(ctx.guild, GuildSetting.WARNING_ROLE)

        if role is None:
            role = await ctx.guild.create_role(
                name="Warning", color=Color.darker_grey()
            )
            crud.set_guild_setting(ctx.guild.id, GuildSetting.WARNING_ROLE, role.id)

        for member in members:
            await self.moderate(
                ctx,
                cb(member.add_roles, role),
                ModerationType.WARN,
                reason,
                member,
                "📢",
            )

    @command(
        help="Elimina los últimos [cantidad] mensajes o el último si ningún argumento es usado. "
        "Si se especifica un miembro, [cantidad] sera la cantidad de mensajes a revisar pero puede o no ser"
        "la cantidad de mensajes eliminados del miembro.",
        usage="[cantidad] [miembro]",
    )
    @has_permissions(manage_messages=True)
    async def clear(
        self, ctx: Context, amount: int = 1, member: Optional[MentionedMember] = None
    ):
        confirm = await Confirm(f"¿Estás seguro de eliminar {amount} mensajes?").prompt(
            ctx
        )

        await ctx.message.delete()

        if not confirm:
            return

        def is_member(message: Message):
            return message.author == member

        check = None
        if member:
            check = is_member

        await ctx.channel.purge(limit=amount, check=check)

        embed = Embed(
            title="Mensajes eliminados! ✅",
            description=f"{amount} mensajes han sido eliminados satisfactoriamente\n"
            f"Este mensaje va a ser eliminado en 5 segundos",
            color=Color.red(),
        )

        await ctx.send(embed=embed, delete_after=5)

    @command(help="Prohibe un usuario en el servidor", usage=usage)
    @has_permissions(ban_members=True)
    async def ban(
        self,
        ctx: Context,
        members: Greedy[MentionedMember],
        duration: Optional[Duration] = None,
        *,
        reason: str,
    ):
        for member in members:
            await self.moderate(
                ctx,
                member.ban,
                ModerationType.BAN,
                reason,
                member,
                "🔨",
                duration,
                member.unban,
            )

    @command(
        help="Expulsa a un usuario del servidor", usage=usage2, aliases=["expulsar"],
    )
    @has_permissions(kick_members=True)
    async def kick(
        self, ctx: Context, members: Greedy[MentionedMember], *, reason: str
    ):
        for member in members:
            await self.moderate(
                ctx, member.kick, ModerationType.KICK, reason, member, "⛔"
            )

    @command(
        help="Evita que un usuario envie mensajes o entre a canales de voz", usage=usage
    )
    @has_permissions(manage_messages=True)
    async def mute(
        self,
        ctx: Context,
        members: Greedy[MentionedMember],
        duration: Optional[Duration] = None,
        *,
        reason: str,
    ):
        role = get_role(ctx.guild, GuildSetting.MUTED_ROLE)

        if role is None:
            role = await ctx.guild.create_role(name="Muted", color=Color.dark_grey())

            overwrite = PermissionOverwrite(send_messages=False, speak=False)
            for channel in ctx.guild.channels:
                await channel.set_permissions(role, overwrite=overwrite)

            crud.set_guild_setting(ctx.guild.id, GuildSetting.MUTED_ROLE, role.id)

        for member in members:
            await self.moderate(
                ctx,
                cb(member.add_roles, role),
                ModerationType.MUTE,
                reason,
                member,
                "🔇",
                duration,
                cb(member.remove_roles, role),
            )
