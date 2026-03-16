# magic_cog.py
from typing import Optional, List, Tuple, Dict, Any
import re, random, ast, math
from discord.ext import commands

from utils import make_embed, json_safe_read, json_safe_write, _norm, int_like, first_int_from
from dc import dc_links, slots_path, spells_path, dc_get_creature_cached

# ---------- storage ----------
def load_slots_store(cid: str) -> dict:
    data = json_safe_read(slots_path(cid), None)
    if isinstance(data, dict):
        for i in range(1, 10):
            data.setdefault(str(i), {"max": 0, "used": 0})
        return data
    return {str(i): {"max": 0, "used": 0} for i in range(1, 10)}

def save_slots_store(cid: str, store: dict):
    json_safe_write(slots_path(cid), store)

def load_spells_list(cid: str) -> List[str]:
    data = json_safe_read(spells_path(cid), {"list": []})
    return [str(x) for x in data.get("list", [])]

def save_spells_list(cid: str, spells: List[str]):
    json_safe_write(spells_path(cid), {"list": sorted(set(spells))})

# ---------- seed / collect ----------
_SPELL_LVL_REGEXES = [
    re.compile(r"(?:^|\s)([1-9])(?:st|nd|rd|th)?\s*(?:level)?\s*spell\s*slots?", re.I),
    re.compile(r"spell\s*slots?\s*(?:\(|\-|\s)*([1-9])(?:st|nd|rd|th)?", re.I),
    re.compile(r"pact\s*magic.*slot\s*level\s*([1-9])", re.I),
    re.compile(r"(?:^|\s)([1-9])(?:st|nd|rd|th)?\s*Level\b", re.I),  # "1st Level", "2nd Level" (DiceCloud TLoE/JSSS)
]

def guess_level_from_name(name: str) -> Optional[int]:
    n = name or ""
    for rx in _SPELL_LVL_REGEXES:
        m = rx.search(n)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None

def _slot_level_from_property(p: dict) -> Optional[int]:
    """Get spell slot level 1-9 from a creatureProperty (name regex or attributeType + spellSlotLevel)."""
    name = p.get("name") or ""
    lvl = guess_level_from_name(name)
    if lvl and 1 <= lvl <= 9:
        return lvl
    if p.get("attributeType") == "spellSlot":
        node = p.get("spellSlotLevel")
        if isinstance(node, dict):
            lvl = int_like(node.get("value"))
        else:
            lvl = int_like(node)
        if lvl and 1 <= lvl <= 9:
            return lvl
        lvl = guess_level_from_name(name)
        if lvl and 1 <= lvl <= 9:
            return lvl
    return None


async def seed_slots_from_cache(cid: str) -> dict:
    data = await dc_get_creature_cached(cid)
    store = load_slots_store(cid)
    props = data.get("creatureProperties") or []
    found_any = False
    for p in props:
        lvl = _slot_level_from_property(p)
        if not lvl:
            continue
        candidates_max = [p.get("max"), p.get("maximum"), p.get("limit"), p.get("usesMax"), p.get("total"), p.get("available"), p.get("value")]
        max_v = 0
        for c in candidates_max:
            iv = int_like(c)
            if iv:
                max_v = iv
                break
        if max_v:
            k = str(lvl)
            prev_used = int(store.get(k, {}).get("used", 0))
            store[k] = {"max": max_v, "used": min(prev_used, max_v)}
            found_any = True
    if found_any:
        save_slots_store(cid, store)
    return store

async def collect_spells_from_cache(cid: str) -> List[str]:
    data  = await dc_get_creature_cached(cid)
    props = data.get("creatureProperties") or []
    tuples = []
    for p in props:
        if (p.get("type") == "spell") and p.get("name"):
            lvl = int_like(p.get("level")) or 99
            tuples.append((lvl, p["name"].strip()))
    seen = {}
    for lvl, name in tuples:
        seen[name.lower()] = (lvl, name)
    ordered = [name for lvl, name in sorted(seen.values(), key=lambda t: (t[0], t[1].lower()))]
    save_spells_list(cid, ordered)
    return ordered

async def collect_prepared_spells_from_cache(cid: str) -> List[str]:
    data  = await dc_get_creature_cached(cid)
    props = data.get("creatureProperties") or []
    prepared = []
    for p in props:
        if p.get("type") != "spell":
            continue
        flag = p.get("prepared") or p.get("isPrepared") or p.get("equipped")
        if isinstance(flag, bool) and flag or isinstance(flag, str) and flag.lower() in {"1","true","yes","y","on"}:
            nm = (p.get("name") or "").strip()
            if nm:
                prepared.append(nm)
    uniq = {}
    for s in prepared:
        uniq[s.lower()] = s
    return sorted(uniq.values(), key=str.lower)

# ---------- rendering ----------
def slot_circles(max_v: int, used: int) -> str:
    ready = max(0, max_v - used); used = min(max_v, max(0, used))
    dots = "●" * ready + "○" * used
    return dots if dots else "—"

def render_slots_embed(title: str, store: dict):
    import discord
    from config import EMBED_COLOR
    embed = discord.Embed(title=title, color=EMBED_COLOR)
    for lvl in range(1, 10):
        k = str(lvl)
        max_v = int(store.get(k, {}).get("max", 0))
        used  = int(store.get(k, {}).get("used", 0))
        if max_v <= 0:
            continue
        embed.add_field(name=f"Level {lvl}", value=slot_circles(max_v, used) + f"  ({max_v - used}/{max_v})", inline=False)
    if not embed.fields:
        embed.description = "No slots configured. Try `!slots sync` or `!slots setmax <level> <N>`."
    return embed

# ---------- brace-template evaluator ----------
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_UNARY  = (ast.UAdd, ast.USub)
_ALLOWED_FUNCS  = {"max": max, "min": min, "round": round, "abs": abs, "floor": math.floor, "ceil": math.ceil}

def _safe_eval_int(expr: str, env: Dict[str, int]) -> Optional[int]:
    try:
        node = ast.parse(str(expr), mode="eval")
    except Exception:
        return None

    def _ev(n):
        if isinstance(n, ast.Expression):
            return _ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return int(n.value)
        if isinstance(n, ast.Num):
            return int(n.n)
        if isinstance(n, ast.Name):
            if n.id in env:
                return int(env[n.id])
            return None
        if isinstance(n, ast.BinOp) and isinstance(n.op, _ALLOWED_BINOPS):
            l = _ev(n.left); r = _ev(n.right)
            if l is None or r is None: return None
            if isinstance(n.op, ast.Add):      return int(l + r)
            if isinstance(n.op, ast.Sub):      return int(l - r)
            if isinstance(n.op, ast.Mult):     return int(l * r)
            if isinstance(n.op, ast.Div):      return int(l / r)
            if isinstance(n.op, ast.FloorDiv): return int(l // r)
            if isinstance(n.op, ast.Mod):      return int(l % r)
            if isinstance(n.op, ast.Pow):      return int(l ** r)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, _ALLOWED_UNARY):
            v = _ev(n.operand)
            if v is None: return None
            if isinstance(n.op, ast.UAdd): return int(+v)
            if isinstance(n.op, ast.USub): return int(-v)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _ALLOWED_FUNCS:
            args = [_ev(a) for a in n.args]
            if any(a is None for a in args): return None
            try:
                return int(_ALLOWED_FUNCS[n.func.id](*args))
            except Exception:
                return None
        return None

    out = _ev(node)
    return int(out) if out is not None else None

def _normalize_template_token(token: str) -> str:
    t = (token or "").strip()
    if t.startswith("#"): t = t[1:]
    t = t.replace("spellList.abilityMod", "abilityMod")
    return t

def _replace_braces_with_numbers(text: str, env: Dict[str, int]) -> str:
    if not isinstance(text, str) or not text:
        return text

    def repl(m):
        raw = m.group(1)
        tok = _normalize_template_token(raw)
        if tok == "abilityMod" and "abilityMod" not in env:
            return "your spellcasting ability modifier"
        val = _safe_eval_int(tok, env)
        return str(val) if val is not None else m.group(0)

    return re.sub(r"\{([^{}]+)\}", repl, text)

def _extract_template_dice(text: str, env: Dict[str, int]) -> List[str]:
    exprs: List[str] = []
    rx = re.compile(r"\{([^{}]+)\}\s*d\s*(\d+)(?:\s*([+\-])\s*\{([^{}]+)\})?", re.I)
    for m in rx.finditer(text or ""):
        left  = _normalize_template_token(m.group(1))
        die   = int(m.group(2))
        op    = m.group(3)
        right = _normalize_template_token(m.group(4) if m.group(4) else "")
        nd = _safe_eval_int(left, env)
        if nd is None or nd <= 0:
            continue
        part = f"{nd}d{die}"
        if op and right:
            rv = _safe_eval_int(right, env)
            if rv is not None and rv != 0:
                # include explicit sign
                part += f"{'+' if rv >= 0 else ''}{rv}"
        exprs.append(part)
    return exprs

# ---------- spellcast helpers ----------
_CAST_LEVEL_RX = re.compile(r"(?:^|\s)(?:at|lvl|level)\s*([1-9])\b", re.I)
_DICE_RX = re.compile(r"\b(\d+)d(\d+)([+-]\d+)?\b", re.I)

def _parse_spellcast_args(tail: str):
    """
    Returns (spell_name, slot_level_int, is_list_flag)
    Accepts:
      - "-list"
      - "Hail of Thorns"
      - "Hail of Thorns 3"
      - "Hail of Thorns at 3" / "lvl 3" / "level 3"
    """
    tail = (tail or "").strip()
    if not tail:
        return None, 1, False
    if tail.lower().startswith("-list"):
        return None, 1, True
    m = _CAST_LEVEL_RX.search(tail)
    lvl = int(m.group(1)) if m else None
    name = tail
    if lvl is None:
        parts = tail.split()
        if parts and parts[-1].isdigit():
            lvl = int(parts[-1]); name = " ".join(parts[:-1]).strip()
    else:
        name = _CAST_LEVEL_RX.sub("", tail).strip()
    name = name.strip() or tail
    lvl = max(1, min(9, lvl or 1))
    return name, lvl, False

def _load_slots(cid: str):
    store = json_safe_read(slots_path(cid), None) or {}
    for i in range(1,10):
        s = store.get(str(i)) or {}
        store[str(i)] = {"max": int_like(s.get("max")) or 0, "used": int_like(s.get("used")) or 0}
    return store

def _save_slots(cid: str, store: dict):
    json_safe_write(slots_path(cid), store)

def _safe_text(val) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        for k in ("text","value","raw","string"):
            v = val.get(k)
            if isinstance(v, str):
                return v
    return ""

def _bundle_for_spell(data: dict, qname: str) -> Dict[str, Any]:
    """
    Return related nodes for a spell name:
      {"spell": spell_node_or_None, "rolls": [roll_nodes], "saving": saving_node_or_None}
    """
    qn = _norm(qname)
    props = data.get("creatureProperties") or []
    spell_node = None
    candidates = [p for p in props if p.get("type") == "spell" and isinstance(p.get("name"), str)]
    exact = [p for p in candidates if _norm(p.get("name")) == qn]
    starts = [p for p in candidates if _norm(p.get("name")).startswith(qn)]
    contains = [p for p in candidates if qn in _norm(p.get("name"))]
    for lst in (exact, starts, contains):
        if lst:
            spell_node = lst[0]; break
    roll_nodes = [p for p in props if p.get("type") == "roll" and isinstance(p.get("name"), str) and qn in _norm(p.get("name"))]
    saving_nodes = [p for p in props if p.get("type") == "savingThrow" and isinstance(p.get("name"), str) and qn in _norm(p.get("name"))]
    saving_node = saving_nodes[0] if saving_nodes else None
    return {"spell": spell_node, "rolls": roll_nodes, "saving": saving_node}

def _collect_damage_exprs(bundle: Dict[str, Any], slot_level: int, ability_mod: Optional[int]) -> List[str]:
    """
    Build dice expressions like "2d6+3" from roll nodes or text.
    Also parse brace-template dice in descriptions using slotLevel/abilityMod.
    """
    exprs: List[str] = []

    # From explicit roll nodes
    for rn in bundle.get("rolls", []):
        val = rn.get("value")
        if isinstance(val, str) and any(ch.isdigit() for ch in val):
            expr = val
        else:
            expr = None
            if isinstance(rn.get("dice"), str):
                expr = rn["dice"]
            else:
                nd = int_like(rn.get("numDice"))
                ds = int_like(rn.get("dieSize"))
                flat = int_like(rn.get("flat")) or 0
                if nd and ds:
                    expr = f"{nd}d{ds}" + (f"+{flat}" if flat else "")
        if isinstance(expr, str):
            expr = re.sub(r"\(?\bslotLevel\b\)?", str(slot_level), expr, flags=re.I)
            expr = re.sub(r"\s+", "", expr)
            if _DICE_RX.fullmatch(expr):
                exprs.append(expr)

    # From templated descriptions
    sp = bundle.get("spell") or {}
    raw_desc = ""
    for key in ("summary","description","text","notes","higherLevel","effect"):
        s = _safe_text(sp.get(key))
        if s and len(s) > len(raw_desc):
            raw_desc = s

    env = {"slotLevel": int(slot_level)}
    if ability_mod is not None:
        env["abilityMod"] = int(ability_mod)
    exprs.extend(_extract_template_dice(raw_desc, env))

    # Also pick up any plain "XdY(+Z)" occurrences
    for key in ("summary","description","text","notes","higherLevel","effect"):
        s = _safe_text(sp.get(key))
        if s:
            for m in _DICE_RX.finditer(s):
                exprs.append(m.group(0))

    seen = set(); out = []
    for e in exprs:
        e = e.replace(" ", "")
        if e not in seen:
            seen.add(e); out.append(e)
    return out

def _spell_attack_bonus_hint(data: dict, bundle: Dict[str, Any]) -> Optional[int]:
    sp = bundle.get("spell") or {}
    sname = sp.get("name")
    props = data.get("creatureProperties") or []
    if sname:
        acts = [p for p in props if p.get("type") == "action" and isinstance(p.get("name"), str) and _norm(p.get("name")) == _norm(sname)]
        if acts:
            node = acts[0]
            for key in ("attackBonus","toHit","hitBonus","bonus"):
                iv = int_like(node.get(key))
                if iv is not None:
                    return iv
    creature = (data.get("creatures") or [{}])[0]
    for path in (("spellAttackBonus",), ("stats","spellAttackBonus"), ("stats","spellAttack")):
        cur = creature
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        iv = int_like(cur)
        if iv is not None:
            return iv
    return None

def _spell_save_dc_hint(data: dict, bundle: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    saving = bundle.get("saving")
    if isinstance(saving, dict):
        dc_obj = saving.get("saveDC") or {}
        dc_val = int_like(dc_obj.get("value")) or int_like(dc_obj.get("calculatedValue")) or int_like(dc_obj.get("baseValue"))
        ab = saving.get("stat") or saving.get("saveAbility") or saving.get("save")
        if isinstance(ab, str):
            ab_low = ab.lower()
            for key, abbr in [("strength","STR"),("dexterity","DEX"),("constitution","CON"),("intelligence","INT"),("wisdom","WIS"),("charisma","CHA")]:
                if key in ab_low:
                    ab = abbr; break
        return dc_val, ab
    creature = (data.get("creatures") or [{}])[0]
    for path in (("spellSaveDC",), ("stats","spellSaveDC")):
        cur = creature
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        iv = int_like(cur)
        if iv is not None:
            return iv, None
    return None, None

def _roll_expr(expr: str):
    m = _DICE_RX.fullmatch(expr.strip())
    if not m:
        return None, ""
    nd, ds, mod = int(m.group(1)), int(m.group(2)), m.group(3)
    rolls = [random.randint(1, ds) for _ in range(nd)]
    total = sum(rolls)
    modv = int(mod) if mod else 0
    total += modv
    br = f"{expr}: [{', '.join(map(str, rolls))}]" + (f" {modv:+d}" if modv else "")
    return total, br

def _spell_description_text(spell_node: dict) -> str:
    if not isinstance(spell_node, dict):
        return ""
    for key in ("summary","description","text","effect","notes"):
        s = _safe_text(spell_node.get(key))
        if s:
            return s
    return ""

def _list_spells_from_snapshot(data: dict) -> List[dict]:
    out = []
    for p in (data.get("creatureProperties") or []):
        if p.get("type") != "spell" or not p.get("name"):
            continue
        name = p["name"].strip()
        lvl = int_like(p.get("level")) or 0
        desc = _spell_description_text(p)
        out.append({"name": name, "level": int(lvl), "desc": desc})
    best: Dict[str, dict] = {}
    for s in sorted(out, key=lambda x: (x["level"], x["name"].lower())):
        best.setdefault(s["name"].lower(), s)
    return list(best.values())

# ---------- NEW helpers for abilities + cleaning ----------
def _spellcasting_ability_mod(data: dict) -> Tuple[Optional[int], Optional[str]]:
    """Return (mod, ability_abbr or None) for spellcasting."""
    creature = (data.get("creatures") or [{}])[0]
    stats = creature.get("stats") or {}
    abilities = stats.get("abilities") or creature.get("abilities") or {}

    # direct fields if present
    for key in ("spellcastingAbilityMod", "spellcastingMod", "spellAbilityMod"):
        v = int_like(stats.get(key)) or int_like(creature.get(key))
        if v is not None:
            return int(v), None

    ab = stats.get("spellcastingAbility") or creature.get("spellcastingAbility")
    abbr = None
    if isinstance(ab, str) and ab.strip():
        low = ab.strip().lower()
        if   low.startswith("str"): abbr = "STR"
        elif low.startswith("dex"): abbr = "DEX"
        elif low.startswith("con"): abbr = "CON"
        elif low.startswith("int"): abbr = "INT"
        elif low.startswith("wis"): abbr = "WIS"
        elif low.startswith("cha"): abbr = "CHA"

    def get_mod_for(abbr: str) -> Optional[int]:
        if not abbr: return None
        key = abbr.lower()[:3]
        v = int_like(stats.get(f"{key}Mod"))
        if v is not None: return int(v)
        v = int_like((abilities.get(key) or {}).get("mod"))
        if v is not None: return int(v)
        v = int_like(((creature.get("abilities") or {}).get(key) or {}).get("mod"))
        if v is not None: return int(v)
        return None

    if abbr:
        v = get_mod_for(abbr)
        if v is not None:
            return v, abbr

    # fallback from DC = 8 + prof + mod
    save_dc = int_like(stats.get("spellSaveDC")) or int_like(creature.get("spellSaveDC"))
    prof   = int_like(stats.get("proficiencyBonus")) or int_like(creature.get("proficiencyBonus"))
    if (save_dc is not None) and (prof is not None):
        mod = int(save_dc) - 8 - int(prof)
        if -5 <= mod <= 12:
            return mod, abbr

    return None, abbr

def _clean_spell_description(desc: str, slot_level: int, mod: Optional[int]) -> str:
    if not isinstance(desc, str) or not desc:
        return ""
    env = {"slotLevel": int(slot_level)}
    if mod is not None:
        env["abilityMod"] = int(mod)
    desc = _replace_braces_with_numbers(desc, env)
    desc = re.sub(r"\{[^}]+\}", "", desc)
    desc = re.sub(r"\s{2,}", " ", desc).strip()
    return desc

# ---------- 2024 healing profiles ----------
def _healing_profile_2024(name: str) -> Optional[Tuple[int, int, int]]:
    """
    If known healing spell (2024), return (die_size, dice_per_level, flat_bonus).
      Cure Wounds     => (8, 2, 2)  → (slotLevel*2)d8 + 2
      Healing Word    => (4, 2, 2)  → (slotLevel*2)d4 + 2
    """
    n = _norm(name)
    if n == "cure wounds":
        return (8, 2, 2)
    if n == "healing word":
        return (4, 2, 2)
    return None

# ---------- commands ----------
def pick_upcast_level(store: dict, start_level: int) -> Optional[int]:
    for lv in range(start_level, 10):
        k = str(lv)
        max_v = int(store.get(k, {}).get("max", 0))
        used  = int(store.get(k, {}).get("used", 0))
        if max_v > used:
            return lv
    return None

class MagicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="slots", invoke_without_command=True)
    async def slots_group(self, ctx):
        """
        Show spell slots (synced from DiceCloud). Cantrips (level 0) do not use slots.
          !slots           → show current slots
          !slots sync      → pull max/used from DiceCloud
          !slots use <level> [n]   → spend slots
          !slots refund <level> [n] → add slots back
          !slots setmax <level> <count> → set max for a level
          !longrest        → reset all used to 0
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")
        store = load_slots_store(cid)
        embed = render_slots_embed("Spell Slots", store)
        embed.set_footer(text="Tip: !longrest = reset all • !slots refund <level> [n] = add slots back • !slots use <level> [n] = spend • !slots setmax <level> <count> = set max • !slots sync = pull from DiceCloud")
        await ctx.send(embed=embed)

    @slots_group.command(name="sync")
    async def slots_sync(self, ctx):
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 Link first: `!dclink <dicecloud url>`.")
        store = await seed_slots_from_cache(cid)
        await collect_spells_from_cache(cid)
        await ctx.send(embed=render_slots_embed("Spell Slots (synced from DiceCloud)", store))

    @slots_group.command(name="setmax")
    async def slots_setmax(self, ctx, level: int, max_count: int):
        if not (1 <= level <= 9) or max_count < 0:
            return await ctx.send("Usage: `!slots setmax <level 1-9> <count>=0+`")
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 Link first.")
        store = load_slots_store(cid)
        k = str(level)
        used = int(store.get(k, {}).get("used", 0))
        store[k] = {"max": max_count, "used": min(used, max_count)}
        save_slots_store(cid, store)
        await ctx.send(embed=render_slots_embed("Spell Slots (updated)", store))

    @slots_group.command(name="use")
    async def slots_use(self, ctx, level: int, n: int = 1):
        if not (1 <= level <= 9) or n <= 0:
            return await ctx.send("Usage: `!slots use <level 1-9> [n]`")
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 Link first.")
        store = load_slots_store(cid)
        k = str(level)
        max_v = int(store.get(k, {}).get("max", 0))
        used  = int(store.get(k, {}).get("used", 0))
        if max_v <= 0:
            return await ctx.send(f"No Level {level} slots configured.")
        if used + n > max_v:
            return await ctx.send(f"Not enough Level {level} slots. ({max_v - used}/{max_v} left)")
        store[k]["used"] = used + n
        save_slots_store(cid, store)
        await ctx.send(embed=render_slots_embed("Spell Slots (spent)", store))

    @slots_group.command(name="refund")
    async def slots_refund(self, ctx, level: int, n: int = 1):
        if not (1 <= level <= 9) or n <= 0:
            return await ctx.send("Usage: `!slots refund <level 1-9> [n]`")
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 Link first.")
        store = load_slots_store(cid)
        k = str(level)
        used = int(store.get(k, {}).get("used", 0))
        store.setdefault(k, {"max": 0, "used": 0})
        store[k]["used"] = max(0, used - n)
        save_slots_store(cid, store)
        await ctx.send(embed=render_slots_embed("Spell Slots (refunded)", store))

    @commands.command(name="longrest")
    async def longrest_cmd(self, ctx):
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 Link first.")
        store = load_slots_store(cid)
        for k, v in store.items():
            v["used"] = 0
        save_slots_store(cid, store)
        await ctx.send(embed=render_slots_embed("Spell Slots (long rest)", store))

    @commands.command(name="spellcast")
    async def spellcast_cmd(self, ctx, *, tail: str = ""):
        """
        Cast a spell and optionally spend a slot. Cantrips (level 0) do not consume slots.
          !spellcast -list
          !spellcast Cure Wounds
          !spellcast Cure Wounds 3  (or "at 3") — upcast
        Default slot level 1 if not specified. Slots synced/refund via !slots.

        Healing (2024): Cure Wounds → (slotLevel*2)d8+2; Healing Word → (slotLevel*2)d4+2.
        Cleans DiceCloud {slotLevel}/{abilityMod} in text; rolls damage when present.
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")

        name_or_none, slot_level, list_flag = _parse_spellcast_args(tail)

        # List spells (with resolved templates at L1)
        if list_flag:
            try:
                data = await dc_get_creature_cached(cid)
            except Exception as e:
                return await ctx.send(f"⚠️ DiceCloud error: {e}")
            mod_val, _ = _spellcasting_ability_mod(data)
            spells = _list_spells_from_snapshot(data)
            if not spells:
                return await ctx.send("No spells found on your snapshot.")
            body_lines = []
            for s in spells[:25]:
                lvl = s["level"]
                desc = s["desc"] or ""
                desc_clean = _clean_spell_description(desc, 1, mod_val)
                desc_short = (desc_clean[:180] + "…") if len(desc_clean) > 200 else desc_clean
                body_lines.append(f"**{s['name']}** (L{lvl}) — {desc_short}" if desc_short else f"**{s['name']}** (L{lvl})")
            more = len(spells) - len(body_lines)
            if more > 0:
                body_lines.append(f"…and {more} more")
            e = make_embed("Your Spells", "\n".join(body_lines))
            return await ctx.send(embed=e)

        if not name_or_none:
            return await ctx.send("Usage: `!spellcast -list` or `!spellcast <name> [at N|N]`")

        # Snapshot
        try:
            data = await dc_get_creature_cached(cid)
        except Exception as e:
            return await ctx.send(f"⚠️ DiceCloud error: {e}")

        bundle = _bundle_for_spell(data, name_or_none)
        spell_node = bundle.get("spell")
        display_name = (spell_node or {}).get("name") or name_or_none

        if not spell_node:
            return await ctx.send(f"⚠️ I can't find a spell named `{name_or_none}` on your sheet. Try `!spellcast -list`.")

        spell_level = int_like((spell_node or {}).get("level"))
        if spell_level is None:
            spell_level = 0
        is_cantrip = spell_level == 0

        if is_cantrip:
            slot_level = 0
        else:
            # Slots: try requested level, else auto-upcast to first available
            slots = _load_slots(cid)
            lvl_key = str(slot_level)
            if int(slots.get(lvl_key, {}).get("max", 0)) - int(slots.get(lvl_key, {}).get("used", 0)) <= 0:
                alt = pick_upcast_level(slots, slot_level)
                if alt is None:
                    max_v = int(slots.get(lvl_key, {}).get("max", 0))
                    used  = int(slots.get(lvl_key, {}).get("used", 0))
                    return await ctx.send(f"❌ No L{slot_level}+ spell slots remaining. (L{slot_level}: {max_v-used}/{max_v} left)")
                slot_level = alt
                lvl_key = str(slot_level)

            # Spend the slot
            slots[lvl_key]["used"] = int(slots[lvl_key]["used"]) + 1
            _save_slots(cid, slots)

        # Roll / text
        atk_bonus = _spell_attack_bonus_hint(data, bundle)
        dc_val, dc_ability = _spell_save_dc_hint(data, bundle)
        ability_mod, _ability = _spellcasting_ability_mod(data)

        lines = []
        title = f"Cast: {display_name} (Cantrip)" if is_cantrip else f"Cast: {display_name} (Level {slot_level})"

        # 2024 healing path (preferred) — cantrips don't scale
        heal_prof = _healing_profile_2024(display_name)
        if heal_prof and not is_cantrip:
            die_size, dice_per_level, flat = heal_prof
            dice_n = int(slot_level) * int(dice_per_level)   # e.g., 2*slotLevel
            expr = f"{dice_n}d{die_size}" + (f"+{flat}" if flat else "")
            tot, br = _roll_expr(expr)
            if tot is not None:
                lines.append(f"**Healing:** {br} = **{tot}**")
        elif not heal_prof:
            # Non-healing: attack/DC and damage rolls (if any)
            if atk_bonus is not None:
                d20 = random.randint(1, 20)
                tohit = d20 + int(atk_bonus)
                crit_note = " — **CRIT!**" if d20 == 20 else (" — **MISS**" if d20 == 1 else "")
                lines.append(f"**Spell Attack:** d20({d20}) + {atk_bonus} = **{tohit}**{crit_note}")
            if dc_val:
                abbr = f" {str(dc_ability).upper()}" if dc_ability else ""
                lines.append(f"**Save DC:** **{dc_val}**{abbr}")

            dmg_exprs = _collect_damage_exprs(bundle, slot_level, ability_mod)
            if dmg_exprs:
                for expr in dmg_exprs[:4]:
                    tot, br = _roll_expr(expr)
                    if tot is not None:
                        lines.append(f"**Damage:** {br} = **{tot}**")

        # Description (clean DiceCloud placeholders)
        desc = _spell_description_text(spell_node)
        if desc:
            desc_clean = _clean_spell_description(desc, slot_level, ability_mod)
            if desc_clean:
                desc_short = desc_clean if len(desc_clean) <= 800 else (desc_clean[:780] + "…")
                lines.append(f"\n*{desc_short}*")

        if not is_cantrip:
            slots = _load_slots(cid)
            lvl_key = str(slot_level)
            max_v = int(slots[lvl_key]["max"])
            used  = int(slots[lvl_key]["used"])
            left = max_v - used
            lines.append(f"\nSlots L{slot_level} remaining: **{left}/{max_v}**")

        e = make_embed(title, "\n".join(lines))
        await ctx.send(embed=e)

async def setup(bot):
    await bot.add_cog(MagicCog(bot))
