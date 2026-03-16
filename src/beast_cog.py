# beast_cog.py
from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any
import re
from discord.ext import commands

from utils import make_embed, _norm
from dc import dc_links

# modules_Beast helpers
from modules_Beast.beast_store import load_beast, save_beast, load_charsheet
from modules_Beast.beast_derive import (
    compute_beast_from_library, explain_linear_formula, parts_from_formula, eval_formula
)
from modules_Beast.beast_skills import SKILL_TO_ABILITY, ability_key, skill_key
from modules_Beast.beast_rolls import roll_d20, roll_dice, format_d20_detail, format_damage_line


# ---- damage type normalization (friendly synonyms) ----
_DAMAGE_TYPES = {
    "slashing": {"slash", "slashing"},
    "piercing": {"pierce", "stab", "piercing"},
    "bludgeoning": {"blunt", "club", "bludgeon", "bludgeoning"},
    "acid": {"acid"},
    "cold": {"cold", "frost", "ice"},
    "fire": {"fire", "flame", "burn"},
    "lightning": {"lightning"},
    "thunder": {"thunder", "sonic"},
    "necrotic": {"necrotic"},
    "radiant": {"radiant"},
    "psychic": {"psychic", "mind"},
    "force": {"force"},
    "poison": {"poison", "toxin"},
}
def _normalize_damage_type(s: str) -> Optional[str]:
    q = _norm(s)
    if q in _DAMAGE_TYPES:
        return q
    for canon, alts in _DAMAGE_TYPES.items():
        if q in alts:
            return canon
    return None

def _list_damage_types() -> str:
    return ", ".join(sorted(_DAMAGE_TYPES.keys()))

# ---- collect human-readable description text for an attack profile ----
def _attack_descriptions(profile: Dict[str, Any]) -> str:
    """
    Returns a short description for an attack profile.
    Priority:
      1) profile["note"]
      2) any notes under profile["on_hit_extra"].*["note"] (joined)
    """
    texts: List[str] = []
    base = (profile or {}).get("note")
    if base:
        texts.append(str(base))

    extra = (profile or {}).get("on_hit_extra") or {}
    for _, sub in extra.items():
        note = (sub or {}).get("note")
        if note:
            texts.append(str(note))

    return "\n".join(t for t in texts if t)

def _unquote(s: str) -> str:
    if not s:
        return s
    if (s[0] == s[-1]) and s[0] in {"'", '"'}:
        return s[1:-1]
    return s

def _target_possessive(name: str) -> str:
    """Return the possessive form of a name: James -> James', Bugman -> Bugman's."""
    if not name:
        return name
    return f"{name}'" if name[-1] in "sS" else f"{name}'s"

def _replace_pronouns_with_target(text: str, target: Optional[str]) -> str:
    """
    Replace whole-word 'yours' -> target's, 'your' -> target's, and 'you' -> target.
    Preserves casing (YOU/You/you) in the replacement.
    """
    if not text or not target:
        return text

    poss = _target_possessive(target)

    def style_like(word: str, repl: str) -> str:
        if word.isupper():
            return repl.upper()
        if word[0].isupper():
            return repl[0].upper() + repl[1:]
        return repl

    def yours_repl(m: re.Match) -> str:
        return style_like(m.group(0), poss)

    def your_repl(m: re.Match) -> str:
        return style_like(m.group(0), poss)

    def you_repl(m: re.Match) -> str:
        return style_like(m.group(0), target)

    # Order matters: 'yours' -> 'your' -> 'you'
    text = re.sub(r"\byours\b", yours_repl, text, flags=re.IGNORECASE)
    text = re.sub(r"\byour\b",  your_repl,  text, flags=re.IGNORECASE)
    text = re.sub(r"\byou\b",   you_repl,   text, flags=re.IGNORECASE)
    return text


class BeastCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------------- Main card ----------------
    @commands.command(name="beast")
    async def beast_cmd(self, ctx, *args):
        """
        !beast
        !beast -help
        !beast -set -name "Fen" -type land|air|sea -photo https://... [-damagetype slashing]
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")

        # help
        if args and _norm(args[0]) == "-help":
            lines = [
                "• `!beast` — show your companion card",
                "• `!beast -set -name \"NAME\" -type <land|air|sea> -photo <url> [-damagetype <type>]`",
                "• `!beasthp +N` / `-N` / `set N` / `fill`",
                "• `!beastcheck <skill|ability> [-adv|-dis] [-prof]`",
                "• `!beastsave <ability> [-adv|-dis] [-prof]`",
                "• `!beastattack [-adv|-dis] [-charge] [-t TARGET] [attack name]`",
            ]
            e = make_embed("Primal Companion — Commands", "\n".join(lines), None)
            return await ctx.send(embed=e)

        # load data
        beast = load_beast(cid)
        sheet = load_charsheet(cid)
        derived = compute_beast_from_library(cid, beast.get("type", "land"), sheet)

        # ensure hp_current exists (default to hp_max)
        if beast.get("hp_current") is None:
            beast["hp_current"] = int(derived["hp_max"])
            save_beast(cid, beast)

        # Handle -set flags (includes -damagetype)
        if args and _norm(args[0]) == "-set":
            tokens = list(args[1:])

            def consume(flag: str) -> Optional[str]:
                if flag in tokens:
                    i = tokens.index(flag)
                    if i + 1 < len(tokens):
                        val = tokens[i + 1]
                        del tokens[i:i + 2]
                        return val
                return None

            name_v = consume("-name")
            type_v = consume("-type")
            photo_v = consume("-photo")
            dmg_v = consume("-damagetype")

            if name_v:
                beast["name"] = name_v
            if type_v:
                beast["type"] = type_v.lower()
            if photo_v:
                beast["photo"] = photo_v
            if dmg_v:
                canon = _normalize_damage_type(dmg_v)
                if not canon:
                    return await ctx.send(f"Unknown damage type `{dmg_v}`.\nTry one of: `{_list_damage_types()}`")
                beast["damage_type"] = canon

            if type_v:
                derived = compute_beast_from_library(cid, beast["type"], sheet)
                if int(beast["hp_current"]) > int(derived["hp_max"]):
                    beast["hp_current"] = int(derived["hp_max"])
            save_beast(cid, beast)

        # Build card
        title = beast.get("name") or "Your Companion"
        sub = derived["display_name"]
        e = make_embed(title, sub, None)

        img = beast.get("photo") or derived.get("photo_default")
        if img:
            e.set_image(url=img)

        # ---- Unified HP display (no duplicates) ----
        comp = (sheet.get("companion") or {})
        hp_cur_disp = comp.get("hp_current")
        hp_max_disp = comp.get("hp_max")
        if hp_cur_disp is None:
            hp_cur_disp = beast.get("hp_current") if beast.get("hp_current") is not None else derived["hp_max"]
        if hp_max_disp is None:
            hp_max_disp = derived["hp_max"]
        e.add_field(name="HP", value=f"**{int(hp_cur_disp)} / {int(hp_max_disp)}**", inline=False)

        # Level / PB
        e.add_field(
            name="Ranger / PB",
            value=f"Level **{derived['ranger_level']}** • PB **+{derived['pb']}**",
            inline=True
        )

        # Abilities (beast mods, from library)
        mods = derived["mods"]
        abil_line = " • ".join([f"{k} {mods.get(k, 0):+d}" for k in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]])
        e.add_field(name="Abilities", value=abil_line, inline=False)

        # AC / Init with explanations
        char_name = (sheet.get("profile") or {}).get("name") or "Your Character"
        char_mods = {k: (sheet.get("abilities") or {}).get(k, {}).get("mod", 0) for k in mods.keys()}
        ac_expl = explain_linear_formula(
            derived.get("ac_formula", ""),
            mods,
            char_mods,
            derived["pb"],
            char_name
        )
        ac_line = f"AC **{derived['ac']}**"
        if ac_expl:
            ac_line += f" ({ac_expl})"
        init_line = f"Initiative **{derived['init']:+d}**"
        init_formula = (derived.get("init_formula") or "").strip()
        if init_formula.upper() == "MOD.DEX":
            init_line += " (DEX)"
        elif init_formula:
            init_line += " (from library)"
        e.add_field(name="AC / Init", value=f"{ac_line} • {init_line}", inline=False)

        # Damage type (optional; shown only if set)
        if beast.get("damage_type"):
            e.add_field(name="Damage Type", value=beast["damage_type"].title(), inline=True)

        await ctx.send(embed=e)

    # ---------------- HP ----------------
    @commands.command(name="beasthp")
    async def beasthp_cmd(self, ctx, *args):
        """!beasthp +N / -N / set N / fill"""
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")

        beast = load_beast(cid)
        sheet = load_charsheet(cid)
        derived = compute_beast_from_library(cid, beast.get("type", "land"), sheet)

        if beast.get("hp_current") is None:
            beast["hp_current"] = int(derived["hp_max"])

        if not args:
            return await ctx.send(f"{beast['name']}: **{beast['hp_current']}/{derived['hp_max']}**")

        if len(args) == 1 and args[0].lower() == "fill":
            beast["hp_current"] = int(derived["hp_max"])
        elif len(args) == 2 and args[0].lower() == "set" and args[1].lstrip("-").isdigit():
            v = int(args[1])
            beast["hp_current"] = max(0, min(int(derived["hp_max"]), v))
        elif len(args) == 1 and (args[0].startswith("+") or args[0].startswith("-")) and args[0][1:].isdigit():
            delta = int(args[0])
            beast["hp_current"] = max(0, min(int(derived["hp_max"]), int(beast["hp_current"]) + delta))
        else:
            return await ctx.send("Usage: `!beasthp +N`, `!beasthp -N`, `!beasthp set N`, or `!beasthp fill`")

        save_beast(cid, beast)
        await ctx.send(f"{beast['name']}: **{beast['hp_current']}/{derived['hp_max']}**")

    # ---------------- Checks ----------------
    @commands.command(name="beastcheck")
    async def beastcheck_cmd(self, ctx, *args):
        """!beastcheck <skill|ability> [-adv|-dis] [-prof]"""
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")
        if not args:
            return await ctx.send("Usage: `!beastcheck <skill|ability> [-adv|-dis] [-prof]`")

        beast = load_beast(cid)
        sheet = load_charsheet(cid)
        derived = compute_beast_from_library(cid, beast.get("type", "land"), sheet)

        toks = list(args)
        adv = any(_norm(t) == "-adv" for t in toks)
        dis = any(_norm(t) == "-dis" for t in toks)
        force_prof = any(_norm(t) == "-prof" for t in toks)  # still supported as override text

        target = next((t for t in toks if not t.startswith("-")), None)
        if not target:
            return await ctx.send("Tell me a skill or ability, e.g. `!beastcheck stealth -adv`")

        mods = derived["mods"]
        pb = int(derived["pb"])

        sk = skill_key(target)
        if sk:
            # 2024 Primal Bond: add PB to any ability check the beast makes.
            abil = SKILL_TO_ABILITY[sk]
            base = int(mods.get(abil, 0))
            parts: List[Tuple[str, int]] = [(abil.title(), base), ("PB", pb)]
            kept, rolls, tag = roll_d20(adv, dis)
            detail = format_d20_detail(rolls, tag, parts)
            title_line = f"{beast['name']} makes a {sk.title()} check."
        else:
            # Raw ability check (e.g., STR). Primal Bond still applies → include PB.
            abil_key = ability_key(target)
            if not abil_key:
                return await ctx.send("Unknown skill/ability. Try things like `stealth`, `perception`, `STR`, `DEX`.")
            base = int(mods.get(abil_key, 0))
            parts = [(abil_key, base), ("PB", pb)]
            kept, rolls, tag = roll_d20(adv, dis)
            detail = format_d20_detail(rolls, tag, parts)
            title_line = f"{beast['name']} makes a {abil_key} ability check."

        # Single bold line (embed title) — no separate beast name header
        e = make_embed(title_line, None, None)
        thumb = beast.get("photo") or derived.get("photo_default")
        if thumb:
            e.set_thumbnail(url=thumb)
        e.add_field(name="Result", value=detail, inline=False)
        await ctx.send(embed=e)

    # ---------------- Saves ----------------
    @commands.command(name="beastsave")
    async def beastsave_cmd(self, ctx, *args):
        """!beastsave <ability> [-adv|-dis] [-prof]"""
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")
        if not args:
            return await ctx.send("Usage: `!beastsave <ability> [-adv|-dis] [-prof]`")

        beast = load_beast(cid)
        sheet = load_charsheet(cid)
        derived = compute_beast_from_library(cid, beast.get("type", "land"), sheet)

        toks = list(args)
        adv = any(_norm(t) == "-adv" for t in toks)
        dis = any(_norm(t) == "-dis" for t in toks)

        abil_token = next((t for t in toks if not t.startswith("-")), None)
        abil = ability_key(abil_token) if abil_token else None
        if not abil:
            return await ctx.send("Tell me an ability, e.g. `!beastsave DEX -dis`")

        mods = derived["mods"]
        pb = int(derived["pb"])

        # 2024 Primal Bond: add PB to any saving throw the beast makes.
        base = int(mods.get(abil, 0))
        parts: List[Tuple[str, int]] = [(abil, base), ("PB", pb)]

        kept, rolls, tag = roll_d20(adv, dis)
        detail = format_d20_detail(rolls, tag, parts)

        # Single bold line — no separate header with just the beast name
        title_line = f"{beast['name']} makes a {abil} saving throw."
        e = make_embed(title_line, None, None)
        thumb = beast.get("photo") or derived.get("photo_default")
        if thumb:
            e.set_thumbnail(url=thumb)
        e.add_field(name="Result", value=detail, inline=False)
        await ctx.send(embed=e)

    # ---------------- Attacks ----------------
    @commands.command(name="beastattack", aliases=["beastatk"])
    async def beastattack_cmd(self, ctx, *args):
        """
        !beastattack [-adv|-dis] [-charge] [-t TARGET] [attack name...]
        Defaults to the first attack (or "Beast's Strike" if present).
        When called with no args, shows available attacks with previews
        and each attack's description (note).
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")

        beast = load_beast(cid)
        sheet = load_charsheet(cid)
        derived = compute_beast_from_library(cid, beast.get("type", "land"), sheet)

        toks = list(args)

        # ---------- Helper (no args): show attack list with previews ----------
        if not toks:
            profiles = derived.get("attack_profiles") or []
            e = make_embed("Beast Attacks", None, None)
            thumb = beast.get("photo") or derived.get("photo_default")
            if thumb:
                e.set_thumbnail(url=thumb)

            if not profiles:
                help_lines = [
                    "**Usage**",
                    "`!beastattack [-adv|-dis] [-charge] [-t TARGET] [attack name]`",
                    "",
                    "**Available attacks**",
                    "_(none in library)_",
                ]
                e.add_field(name="Help", value="\n".join(help_lines), inline=False)
                return await ctx.send(embed=e)

            # Build per-attack previews using current sheet/type (level appropriate)
            char_mods = {k: (sheet.get("abilities") or {}).get(k, {}).get("mod", 0) for k in ["STR","DEX","CON","INT","WIS","CHA"]}
            pb = int(derived["pb"])
            beast_mods = derived["mods"]
            char_name = (sheet.get("profile") or {}).get("name") or "Your Character"

            lines: List[str] = []
            for p in profiles:
                name = p.get("name", "Attack")

                # To-hit bonus (preview)
                to_hit_expr = p.get("to_hit_formula") or "PB"
                to_parts = parts_from_formula(to_hit_expr, beast_mods, char_mods, pb, char_name)
                if to_parts is None:
                    bonus = eval_formula(to_hit_expr, {
                        "RANGER_LEVEL": derived["ranger_level"],
                        "PB": pb,
                        "MOD": beast_mods,
                        "CHARMOD": char_mods,
                    })
                    to_txt = f"+{int(bonus)}"
                else:
                    to_txt = f"+{sum(v for _, v in to_parts):d}"

                # Damage preview
                dmg_dice = p.get("damage_dice") or "1"
                dmg_mod_expr = p.get("damage_mod_formula") or "0"
                mp = parts_from_formula(dmg_mod_expr, beast_mods, char_mods, pb, char_name)
                if mp is None:
                    bonus_val = eval_formula(dmg_mod_expr, {
                        "RANGER_LEVEL": derived["ranger_level"],
                        "PB": pb,
                        "MOD": beast_mods,
                        "CHARMOD": char_mods,
                    })
                    mod_txt = f"{int(bonus_val):+d}" if int(bonus_val) != 0 else ""
                else:
                    chunks = [f"{v:+d} ({lbl})" if lbl else f"{v:+d}" for (lbl, v) in mp if v != 0]
                    mod_txt = " " + " ".join(chunks) if chunks else ""

                # Damage type
                dmg_type = (p.get("damage_type") or beast.get("damage_type") or "damage").lower()

                line = f"• **{name}** — to hit {to_txt}; damage {dmg_dice}{mod_txt} {dmg_type}"
                lines.append(line)

                desc = _attack_descriptions(p)
                if desc:
                    lines.append(f"   └ {desc}")

            help_lines = [
                "**Usage**",
                "`!beastattack [-adv|-dis] [-charge] [-t TARGET] [attack name]`",
                "",
                "**Available attacks**",
                *lines,
                "",
                "**Examples**",
                "`!beastattack Beast's Strike`",
                "`!beastattack -adv Beast's Strike`",
                "`!beastattack -charge Beast's Strike -t \"Ogre\"`",
            ]
            e.add_field(name="Help", value="\n".join(help_lines), inline=False)
            return await ctx.send(embed=e)

        # ---------- Execute attack ----------
        # Parse flags
        adv = any(_norm(t) == "-adv" for t in toks)
        dis = any(_norm(t) == "-dis" for t in toks)
        want_charge = any(_norm(t) == "-charge" for t in toks)

        # Extract optional target after '-t' (supports multi-word until next flag)
        target_tokens: List[str] = []
        attack_tokens: List[str] = []
        i = 0
        while i < len(toks):
            t = toks[i]
            if _norm(t) == "-t":
                j = i + 1
                while j < len(toks) and not toks[j].startswith("-"):
                    target_tokens.append(toks[j])
                    j += 1
                i = j
                continue
            attack_tokens.append(t)
            i += 1

        target_name = _unquote(" ".join(target_tokens).strip()) if target_tokens else None

        # Attack name: non-flag tokens from attack_tokens
        name_tokens = [t for t in attack_tokens if not t.startswith("-")]
        atk_name_q = " ".join(name_tokens).strip() if name_tokens else None

        profiles = derived.get("attack_profiles") or []
        chosen = None

        if atk_name_q:
            qn = _norm(atk_name_q)
            for p in profiles:
                if _norm(p.get("name", "")) == qn:
                    chosen = p
                    break
            if not chosen:
                for p in profiles:
                    if _norm(p.get("name", "")).startswith(qn):
                        chosen = p
                        break
            if not chosen and profiles:
                chosen = profiles[0]
        else:
            for p in profiles:
                if _norm(p.get("name", "")) in {"beast's strike", "beasts strike", "beast strike"}:
                    chosen = p
                    break
            if not chosen and profiles:
                chosen = profiles[0]

        if not chosen:
            return await ctx.send("No attack profiles in library for this beast type.")

        # Build environment for formula eval and breakdown
        char_mods = {k: (sheet.get("abilities") or {}).get(k, {}).get("mod", 0) for k in ["STR","DEX","CON","INT","WIS","CHA"]}
        pb = int(derived["pb"])
        beast_mods = derived["mods"]
        char_name = (sheet.get("profile") or {}).get("name") or "Your Character"

        # --- To Hit ---
        to_hit_expr = chosen.get("to_hit_formula") or "PB"
        to_parts = parts_from_formula(to_hit_expr, beast_mods, char_mods, pb, char_name)
        if to_parts is None:
            to_bonus = eval_formula(to_hit_expr, {
                "RANGER_LEVEL": derived["ranger_level"],
                "PB": pb,
                "MOD": beast_mods,
                "CHARMOD": char_mods,
            })
            to_parts = [("bonus", int(to_bonus))]
        kept, rolls, tag = roll_d20(adv, dis)
        tohit_detail = format_d20_detail(rolls, tag, to_parts)

        # --- Damage (on hit) ---
        dmg_dice_expr = chosen.get("damage_dice") or "1"
        dmg_mod_expr = chosen.get("damage_mod_formula") or "0"
        dmg_type = (chosen.get("damage_type") or beast.get("damage_type") or "damage").lower()

        mod_parts = parts_from_formula(dmg_mod_expr, beast_mods, char_mods, pb, char_name)
        if mod_parts is None:
            bonus_val = eval_formula(dmg_mod_expr, {
                "RANGER_LEVEL": derived["ranger_level"],
                "PB": pb,
                "MOD": beast_mods,
                "CHARMOD": char_mods,
            })
            mod_parts = [("bonus", int(bonus_val))] if int(bonus_val) != 0 else []

        dice_total, _dice_rolls = roll_dice(dmg_dice_expr)
        damage_line = format_damage_line(dmg_dice_expr, dice_total, mod_parts, dmg_type)

        # --- Optional Charge extra ---
        extra_lines: List[str] = []
        if want_charge:
            charge = ((chosen.get("on_hit_extra") or {}).get("charge")) or {}
            ex_expr = charge.get("extra_damage_dice") or "1d6"
            ex_total, _ex_rolls = roll_dice(ex_expr)
            extra_lines.append(f"20-ft Charge: {ex_expr} ({ex_total}) = **`{ex_total}`**")

        # Build embed — single bold line (title) without separate beast-name header
        atk_display = chosen.get('name', 'Attack')
        if target_name:
            title_line = f"{beast.get('name') or 'Your Companion'} uses {atk_display} on {target_name}."
        else:
            title_line = f"{beast.get('name') or 'Your Companion'} uses {atk_display}."
        e = make_embed(title_line, None, None)

        thumb = beast.get("photo") or derived.get("photo_default")
        if thumb:
            e.set_thumbnail(url=thumb)

        e.add_field(name="To Hit", value=tohit_detail, inline=False)
        e.add_field(name="Damage", value=damage_line, inline=False)
        if extra_lines:
            e.add_field(name="Extra", value="\n".join(extra_lines), inline=False)

        # Description (with 'yours'/'your'/'you' -> target replacement)
        desc_text = _attack_descriptions(chosen)
        if desc_text and target_name:
            desc_text = _replace_pronouns_with_target(desc_text, target_name)
        if desc_text:
            e.add_field(name="Description", value=desc_text, inline=False)

        await ctx.send(embed=e)


# ---- setup hook ----
async def setup(bot):
    # hot-reload safe
    if bot.get_cog("BeastCog"):
        bot.remove_cog("BeastCog")
    await bot.add_cog(BeastCog(bot))
