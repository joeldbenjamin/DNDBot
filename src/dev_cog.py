# dev_cog.py — !testAs to run a command as another user (by ID or @mention)
from __future__ import annotations

import discord
from discord.ext import commands


class TestAsContext:
    """Minimal context wrapper that overrides ctx.author so commands see the target user's ID."""
    def __init__(self, real_ctx: commands.Context, author: discord.abc.User):
        self._real = real_ctx
        self.author = author
        self.bot = real_ctx.bot
        self.guild = real_ctx.guild
        self.channel = real_ctx.channel
        self.message = real_ctx.message

    async def send(self, *args, **kwargs):
        return await self._real.send(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class DevCog(commands.Cog):
    """Dev-only: !testAs <user> <command> [args...] to run a command as another user."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="testAs", aliases=["testas"])
    async def test_as(self, ctx, user: discord.User, *, remainder: str):
        """
        Run a command as another user. Use their Discord @mention or user ID.
        Example: !testAs @Friend spellcast Fire Bolt
        Example: !testAs 835712883173097502 sync
        The bot uses Discord user ID for linking; this runs the command as that user.
        """
        remainder = (remainder or "").strip()
        if not remainder:
            return await ctx.send("Usage: `!testAs @User <command> [args...]` e.g. `!testAs @Friend spellcast Fire Bolt`")

        tokens = remainder.split()
        # Resolve command (allow subcommands e.g. "slots sync", "slots setmax 1 4")
        two_word = f"{tokens[0]} {tokens[1]}" if len(tokens) >= 2 else None
        command = self.bot.get_command(two_word) if two_word else self.bot.get_command(tokens[0])
        if not command:
            command = self.bot.get_command(tokens[0])
        if not command:
            return await ctx.send("❌ Unknown command. Use e.g. spellcast, whoami, slots, slots sync, sync.")

        # Only take tokens[2:] when we actually resolved a subcommand (e.g. "slots sync").
        # For "spellcast Shield", get_command("spellcast Shield") returns spellcast, so we must use tokens[1:] so "Shield" is passed as tail.
        is_subcommand = isinstance(getattr(command, "parent", None), commands.Group)
        rest = " ".join(tokens[2:]) if two_word and command == self.bot.get_command(two_word) and is_subcommand else " ".join(tokens[1:])
        full_invoke = "!" + remainder

        fake_ctx = TestAsContext(ctx, user)
        params = [k for k in command.clean_params if k not in ("self", "ctx")]

        try:
            await ctx.send(f"🔧 Running as **{user.name}** (id={user.id}): `{full_invoke}`")
            if not params:
                await command.callback(command.cog, fake_ctx)
            elif "tail" in params:
                await command.callback(command.cog, fake_ctx, tail=rest)
            elif "command_name" in params:
                await command.callback(command.cog, fake_ctx, command_name=rest)
            else:
                await command.callback(command.cog, fake_ctx, *rest.split())
        except Exception as e:
            await ctx.send(f"⚠️ Error running as {user.name}: {e}")
            raise


async def setup(bot):
    if bot.get_cog("DevCog"):
        bot.remove_cog("DevCog")
    await bot.add_cog(DevCog(bot))
