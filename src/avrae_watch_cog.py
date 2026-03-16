import re
from discord.ext import commands
from config import AVRAE_ID, NAT1_IMG, NAT20_IMG
from utils import make_embed

class AvraeWatch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # Only react to Avrae’s messages. Do NOT call process_commands here.
        if message.author.id != AVRAE_ID:
            return

        raw = message.content or ""
        for emb in message.embeds:
            if emb.description: raw += " " + emb.description
            for f in emb.fields: raw += " " + f.value
            if emb.footer and emb.footer.text: raw += " " + emb.footer.text

        m = re.search(r'\(([-\d,\s~*`]+)\)', raw)
        if not m:
            return
        nums = [int(n) for n in re.findall(r'\b\d+\b', m.group(1))]
        if not nums:
            return

        if 'kh1' in raw: actual = max(nums)
        elif 'kl1' in raw: actual = min(nums)
        else: actual = nums[0]

        if actual == 1:
            e = make_embed("The gods have shunned someone!", "A natural 1 was rolled.", None)
            e.set_image(url=NAT1_IMG)
            await message.channel.send(embed=e)
        elif actual == 20:
            e = make_embed("The gods have favored someone!", "A natural 20 was rolled.", None)
            e.set_image(url=NAT20_IMG)
            await message.channel.send(embed=e)

async def setup(bot):
    print("[AvraeWatch] setup()")
    await bot.add_cog(AvraeWatch(bot))
