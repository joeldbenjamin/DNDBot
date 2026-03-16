# help_cog.py
import re
from typing import Dict, List

from discord.ext import commands
from utils import make_embed
from config import COMMAND_IMAGE_URL


def _shorten(s: str, max_len: int = 140) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _doc_first_line(cmd: commands.Command) -> str:
    doc = (getattr(cmd.callback, "__doc__", None) or "").strip()
    if not doc:
        return ""
    first = doc.splitlines()[0]
    return _shorten(first, 140)


def _format_cmd_line(prefix: str, cmd: commands.Command) -> str:
    # e.g.  • !beastattack — roll attacks (aliases: beastatk)
    parts: List[str] = []
    parts.append(f"`{prefix}{cmd.name}`")
    desc = _doc_first_line(cmd)
    if desc:
        parts.append(f"— {desc}")
    if cmd.aliases:
        parts.append(f"(aliases: {', '.join(cmd.aliases)})")
    return " ".join(parts)


class HelpCog(commands.Cog):
    """Dynamic help for all D&D bot commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="helpDND", aliases=["helpdnd", "dndhelp"])
    async def help_dnd(self, ctx, *, command_name: str = None):
        """
        Show a complete, auto-generated list of commands.
        Use `!helpDND <command>` for details on a specific command.
        """
        prefix = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else "!"

        # Specific command detail view
        if command_name:
            cmd = self.bot.get_command(command_name)
            if not cmd:
                return await ctx.send(f"❓ I don’t know a command named `{command_name}`.")
            title = f"{prefix}{cmd.name}"
            subtitle = "Command details"
            e = make_embed(title, subtitle, COMMAND_IMAGE_URL)

            # Aliases
            if cmd.aliases:
                e.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in cmd.aliases), inline=False)

            # Cog / Category
            e.add_field(name="Category", value=cmd.cog_name or "General", inline=True)

            # Docstring (full)
            doc = (getattr(cmd.callback, "__doc__", None) or "").strip()
            doc = doc if doc else "—"
            # Keep within a safe size for an embed field
            doc = doc if len(doc) <= 1000 else (doc[:997] + "…")
            e.add_field(name="Help", value=f"```\n{doc}\n```", inline=False)

            return await ctx.send(embed=e)

        # Full command list (grouped by cog)
        groups: Dict[str, List[commands.Command]] = {}
        for cmd in sorted(self.bot.commands, key=lambda c: c.name):
            # Skip commands that are set to hidden
            if getattr(cmd, "hidden", False):
                continue
            # Avoid listing the default discord.py help command if present
            if cmd.name == "help" and cmd.callback.__qualname__.startswith("HelpCommand"):
                continue
            groups.setdefault(cmd.cog_name or "General", []).append(cmd)

        e = make_embed("D-D Bot — Commands", "Auto-generated quick reference", COMMAND_IMAGE_URL)
        e.set_footer(text="Tip: Use !helpDND <command> for detailed help.")
        # Produce one field per cog
        for cog_name in sorted(groups.keys()):
            cmds = groups[cog_name]
            lines = [_format_cmd_line(prefix, c) for c in cmds]
            # Discord embed field limit: 1024 chars — chunk if needed
            chunk = []
            total = 0
            field_index = 1
            for line in lines:
                if total + len(line) + 1 > 1024 and chunk:
                    e.add_field(
                        name=f"{cog_name} ({len(cmds)})" if field_index == 1 else f"{cog_name} (cont.)",
                        value="\n".join(chunk),
                        inline=False,
                    )
                    chunk, total, field_index = [], 0, field_index + 1
                chunk.append("• " + line)
                total += len(line) + 1
            if chunk:
                e.add_field(
                    name=f"{cog_name} ({len(cmds)})" if field_index == 1 else f"{cog_name} (cont.)",
                    value="\n".join(chunk),
                    inline=False,
                )

        await ctx.send(embed=e)


async def setup(bot):
    # Hot-reload safe
    if bot.get_cog("HelpCog"):
        bot.remove_cog("HelpCog")
    await bot.add_cog(HelpCog(bot))
