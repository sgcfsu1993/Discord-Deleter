import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import json
import os
from datetime import datetime, timedelta, timezone

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

PURGE_FILE = "timed_purge.json"

if os.path.exists(PURGE_FILE):
    with open(PURGE_FILE, "r") as f:
        purge_config = json.load(f)
else:
    purge_config = {}

def save_purge_config():
    with open(PURGE_FILE, "w") as f:
        json.dump(purge_config, f, indent=4)

#---------------------------------------------------------------

DATA_FILE = "channel_config.json"
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        channel_config = json.load(f)
else:
    channel_config = {}

def save_config():
    with open(DATA_FILE, "w") as f:
        json.dump(channel_config, f, indent=4)

#---------------------------------------------------------------

ROLE_FILE = "roles.json"

def load_roles():
    if os.path.exists(ROLE_FILE):
        with open(ROLE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_roles(role_dict):
    with open(ROLE_FILE, "w") as f:
        json.dump(role_dict, f, indent=4)

role_map = load_roles()

#---------------------------------------------------------------

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"Im here, no worries.")

# ---------------- Commands ----------------

# Enable channel wide deletion
@bot.command()
@commands.has_permissions(administrator=True)
async def enablechannel(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    if guild_id not in purge_config:
        purge_config[guild_id] = {}

    purge_config[guild_id][channel_id] = {"delay": None }
    save_purge_config()
    await ctx.send(f"{ctx.author.mention} enabled timed purge in {channel.mention}")

# Disable channel
@bot.command()
@commands.has_permissions(administrator=True)
async def disablechannel(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    if guild_id in purge_config and channel_id in purge_config[guild_id]:
        del purge_config[guild_id][channel_id]
        save_purge_config()
        await ctx.send(f"{ctx.author.mention} disabled {channel.mention}")
    else:
        await ctx.send(f"{ctx.author.mention} {channel.mention} is already disabled")

# Add user target (works even if channel is not enabled)
@bot.command()
@commands.has_permissions(administrator=True)
async def addusertarget(ctx, channel: discord.TextChannel, member: discord.Member):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    if guild_id not in channel_config:
        channel_config[guild_id] = {}

    if channel_id not in channel_config[guild_id]:
        channel_config[guild_id][channel_id] = {
            "targets": [],
            "watch_count": 2,
            "current_counts": {}
        }

    if member.id not in channel_config[guild_id][channel_id]["targets"]:
        channel_config[guild_id][channel_id]["targets"].append(member.id)
        channel_config[guild_id][channel_id]["current_counts"][str(member.id)] = 0
        save_config()
        await ctx.send(f"{ctx.author.mention} is now watching {member.mention} in {channel.mention}")
    else:
        await ctx.send(f"{member.mention} is already being watched in {channel.mention}")

# Remove user target
@bot.command()
@commands.has_permissions(administrator=True)
async def removeusertarget(ctx, channel: discord.TextChannel, member: discord.Member):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    if guild_id in channel_config and channel_id in channel_config[guild_id]:
        if member.id in channel_config[guild_id][channel_id]["targets"]:
            channel_config[guild_id][channel_id]["targets"].remove(member.id)
            channel_config[guild_id][channel_id]["current_counts"].pop(str(member.id), None)
            save_config()
            await ctx.send(f"{member.mention} is no longer watched in {channel.mention}")
        else:
            await ctx.send(f"{member.mention} is not being watched in {channel.mention}")
    else:
        await ctx.send(f"{channel.mention} is not enabled for auto-delete")

# Set watch count
@bot.command()
@commands.has_permissions(administrator=True)
async def setwatchcount(ctx, channel: discord.TextChannel, count: int):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)
    if guild_id in channel_config and channel_id in channel_config[guild_id]:
        channel_config[guild_id][channel_id]["watch_count"] = count
        save_config()
        await ctx.send(f"Watch count for {channel.mention} set to {count}")
    else:
        await ctx.send(f"{channel.mention} is not enabled for auto-delete")

# Set delay for a channel purge
@bot.command()
@commands.has_permissions(administrator=True)
async def setpurgetime(ctx, channel: discord.TextChannel, seconds: int):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    if guild_id in purge_config and channel_id in purge_config[guild_id]:
        purge_config[guild_id][channel_id]["delay"] = seconds
        save_purge_config()
        await ctx.send(f"Purge delay for {channel.mention} set to {seconds} seconds.")
    else:
        await ctx.send(f"{channel.mention} does not have timed purge enabled. Use !enablechannel first.")

# Function to purge a channel after a delay
async def delayed_purge(channel: discord.TextChannel, delay: int):
    await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=delay))
    try:
        await channel.purge(limit=None)
    except Exception as e:
        print(f"Failed to purge channel {channel.id}: {e}")

# Show current purge timer for a channel
@bot.command()
@commands.has_permissions(administrator=True)
async def showpurgetime(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    if guild_id in purge_config and channel_id in purge_config[guild_id]:
        delay = purge_config[guild_id][channel_id].get("delay")
        if delay is None:
            await ctx.send(f"{channel.mention} currently has no purge timer set.")
        else:
            await ctx.send(f"Purge timer for {channel.mention} is set to {delay} seconds.")
    else:
        await ctx.send(f"{channel.mention} is not enabled for timed purge. Use !enablechannel first.")

# ---------------- Event ----------------
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    guild_id = str(message.guild.id) if message.guild else None
    channel_id = str(message.channel.id) if message.channel else None

    if not guild_id or not channel_id:
        return

    # ---------------- TIMED CHANNEL PURGE ----------------
    active_timers = getattr(bot, "active_timers", {})
    bot.active_timers = active_timers

    if guild_id in purge_config and channel_id in purge_config[guild_id]:
        delay = purge_config[guild_id][channel_id].get("delay")
        if delay is None:
            pass  # skip timed purge until delay is set
        elif channel_id not in active_timers:
            async def delayed():
                await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=delay))
                try:
                    await message.channel.purge(limit=None)
                except Exception as e:
                    print(f"Failed to purge {message.channel.name}: {e}")
                finally:
                    bot.active_timers.pop(channel_id, None)

            bot.active_timers[channel_id] = bot.loop.create_task(delayed())

    # ---------------- USER TARGET DELETE ----------------
    if guild_id in channel_config and channel_id in channel_config[guild_id]:
        guild_channels = channel_config[guild_id][channel_id]
        targets = guild_channels.get("targets", [])

        if message.author.id in targets:
            uid_str = str(message.author.id)
            current = guild_channels["current_counts"].get(uid_str, 0) + 1
            guild_channels["current_counts"][uid_str] = current

            if current >= guild_channels["watch_count"]:
                try:
                    messages_to_delete = []
                    async for m in message.channel.history(limit=100):
                        if m.author.id == message.author.id:
                            messages_to_delete.append(m)
                            if len(messages_to_delete) >= guild_channels["watch_count"]:
                                break

                    if messages_to_delete:
                        await message.channel.delete_messages(messages_to_delete)

                    guild_channels["current_counts"][uid_str] = 0
                    save_config()
                except Exception as e:
                    print(f"User delete failed: {e}")

    await bot.process_commands(message)


# ---------------- Role Assign ----------------
# (rest of your file remains unchanged)

@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}")

@bot.command(name="defam")
async def defam(ctx, member: discord.Member):
    await ctx.send(f"{member.mention} is a potato")

@bot.command(name="commands")
async def show_commands(ctx):
    help_text = """
**Available Bot Commands**

**Timed Channel Purge**
`!enablechannel #channel` - Enable timed purge in a channel  
`!disablechannel #channel` - Disable timed purge in a channel  
`!setpurgetime #channel <seconds>` - Set how long before the channel is fully purged  
`!showpurgetime #channel` - Show the current purge timer for a channel  

**User Watch Auto-Delete**
`!addusertarget #channel @user` - Watch a specific user in a channel  
`!removeusertarget #channel @user` - Stop watching a specific user  
`!setwatchcount #channel <number>` - Number of messages before that user’s messages are deleted  

**Role Management**
`!addroles <role name> <internal ID>` - Add a role to the assignable roles list (creates it if missing)  
`!roles` - Show all assignable roles and their internal IDs  
`!assign @user <internal ID>` - Assign a role to a user by internal ID  
`!removeroles @user <internal ID>` - Remove a role from a user by internal ID  
`!deleteroles <internal ID>` - Delete a role from the server and remove it from the mapping  

**Fun / Test**
`!hello` - Say hello to the bot  
`!defam @user` - Playfully poke a user ("is a potato")  
"""
    await ctx.send(help_text)

bot.run(token, log_handler=handler, log_level=logging.DEBUG)
