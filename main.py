import enum

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


DATA_FILE = "channel_config.json"
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        channel_config = json.load(f)
else:
    channel_config = {}

def save_config():
    with open(DATA_FILE, "w") as f:
        json.dump(channel_config, f, indent=4)

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

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"Im here, no worries.")

# ---------------- Commands ----------------

# Enable channel-wide deletion
@bot.command()
@commands.has_permissions(administrator=True)
async def enablechannel(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    if guild_id not in channel_config:
        channel_config[guild_id] = {}

    channel_config[guild_id][channel_id] = {
        "targets": [],              # empty = channel wide mode
        "watch_count": 2,           # default threshold
        "current_counts": {"all": 0}
    }
    save_config()
    await ctx.send(f"{ctx.author.mention} enabled {channel.mention} for channel-wide auto-delete.")

# Disable channel
@bot.command()
@commands.has_permissions(administrator=True)
async def disablechannel(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    if guild_id in channel_config and channel_id in channel_config[guild_id]:
        del channel_config[guild_id][channel_id]
        save_config()
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

# ---------------- Event ----------------
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    guild_id = str(message.guild.id) if message.guild else None
    channel_id = str(message.channel.id) if message.channel else None

    if not guild_id or not channel_id:
        await bot.process_commands(message)
        return

    # --- Channel wide deletion ---
    if guild_id in channel_config and channel_id in channel_config[guild_id]:
        config = channel_config[guild_id][channel_id]
        if not config["targets"]:  # empty = channel-wide
            uid_str = "all"
            current = config["current_counts"].get(uid_str, 0) + 1
            config["current_counts"][uid_str] = current

            if current >= config["watch_count"]:
                try:
                    messages_to_delete = []
                    async for m in message.channel.history(limit=100):
                        if (datetime.now(timezone.utc) - m.created_at) < timedelta(days=14):
                            messages_to_delete.append(m)
                            if len(messages_to_delete) >= config["watch_count"]:
                                break
                    if messages_to_delete:
                        await message.channel.delete_messages(messages_to_delete)

                    config["current_counts"][uid_str] = 0
                    save_config()
                except:
                    pass

    # --- User-specific deletion ---
    for guild_channels in channel_config.get(guild_id, {}).values():
        targets = guild_channels.get("targets", [])
        if message.author.id in targets:
            uid_str = str(message.author.id)
            current = guild_channels["current_counts"].get(uid_str, 0) + 1
            guild_channels["current_counts"][uid_str] = current

            if current >= guild_channels["watch_count"]:
                try:
                    messages_to_delete = []
                    async for m in message.channel.history(limit=100):
                        if m.author.id == message.author.id and (datetime.now(timezone.utc) - m.created_at) < timedelta(days=14):
                            messages_to_delete.append(m)
                            if len(messages_to_delete) >= guild_channels["watch_count"]:
                                break
                    if messages_to_delete:
                        await message.channel.delete_messages(messages_to_delete)

                    guild_channels["current_counts"][uid_str] = 0
                    save_config()
                except:
                    pass

    await bot.process_commands(message)

# ---------------- Role Assign ----------------
# To assign roles
@bot.command()
@commands.has_permissions(manage_roles=True)
async def addroles(ctx, role_name: str, internal_id: str):
    guild_id = str(ctx.guild.id)
    if guild_id not in role_map:
        role_map[guild_id] = {}

    # Check if the role already exists
    discord_role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not discord_role:
        try:
            # Create the role with general permissions
            general_perms = discord.Permissions(
                read_messages=True,
                send_messages=True,
                connect=True,
                speak=True,
                view_channel=True
            )
            discord_role = await ctx.guild.create_role(
                name=role_name,
                permissions=general_perms,
                reason=f"Role created by bot for internal ID {internal_id}"
            )
            await ctx.send(f"Created role `{role_name}` in this server with general permissions.")
        except discord.Forbidden:
            await ctx.send("I do not have permission to create roles.")
            return
        except Exception as e:
            await ctx.send(f"Failed to create role: {e}")
            return
    else:
        await ctx.send(f"Role `{role_name}` already exists.")

    # Save the internal ID mapping
    role_map[guild_id][internal_id] = role_name
    save_roles(role_map)
    await ctx.send(f"Added role mapping: {internal_id} -> {role_name}")

@bot.command()
async def roles(ctx):
    guild_id = str(ctx.guild.id)
    if guild_id not in role_map or not role_map[guild_id]:
        await ctx.send("No roles have been added yet.")
        return

    message = "Available roles:\n"
    for internal_id, role_name in role_map[guild_id].items():
        message += f"{internal_id}: {role_name}\n"
    await ctx.send(message)

@bot.command()
async def assign(ctx, member: discord.Member, internal_id: str):
    guild_id = str(ctx.guild.id)
    if guild_id not in role_map or internal_id not in role_map[guild_id]:
        await ctx.send(f"{internal_id} is not a valid role ID in this server.")
        return

    role_name = role_map[guild_id][internal_id]
    discord_role = discord.utils.get(ctx.guild.roles, name=role_name)

    if not discord_role:
        await ctx.send(f"The role `{role_name}` does not exist in this server.")
        return

    try:
        await member.add_roles(discord_role)
        await ctx.send(f"Assigned role `{role_name}` to {member.display_name}")
    except discord.Forbidden:
        await ctx.send("I do not have permission to assign that role.")
    except Exception as e:
        await ctx.send(f"Failed to assign role: {e}")


# To remove member roles
@bot.command()
@commands.has_permissions(manage_roles=True)
async def removeroles(ctx, member: discord.Member, role_id: str):
    guild_id = str(ctx.guild.id)

    # Check if the server has roles mapped
    if guild_id not in role_map or role_id not in role_map[guild_id]:
        await ctx.send(f"{role_id} is not a valid role ID in this server. Use !roles to see available roles.")
        return

    role_name = role_map[guild_id][role_id]
    role = discord.utils.get(ctx.guild.roles, name=role_name)

    if not role:
        await ctx.send(f"The role `{role_name}` does not exist in this server.")
        return

    if role not in member.roles:
        await ctx.send(f"{member.mention} does not have the role `{role.name}`.")
        return

    try:
        await member.remove_roles(role)
        await ctx.send(f"{role.name} has been removed from {member.mention}.")
    except discord.Forbidden:
        await ctx.send("I do not have permission to remove that role.")
    except Exception as e:
        await ctx.send(f"Failed to remove role: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def deleteroles(ctx, internal_id: str):
    guild_id = str(ctx.guild.id)

    # Check if the role exists in the internal mapping
    if guild_id not in role_map or internal_id not in role_map[guild_id]:
        await ctx.send(f"{internal_id} is not a valid role ID in this server. Use !roles to see available roles.")
        return

    role_name = role_map[guild_id][internal_id]
    discord_role = discord.utils.get(ctx.guild.roles, name=role_name)

    if not discord_role:
        # Role doesn't exist in the server but still remove mapping
        await ctx.send(f"Role `{role_name}` does not exist in the server, removing from mapping.")
    else:
        try:
            await discord_role.delete(reason=f"Deleted by bot via internal ID {internal_id}")
            await ctx.send(f"Role `{role_name}` has been deleted from the server.")
        except discord.Forbidden:
            await ctx.send("I do not have permission to delete that role.")
            return
        except Exception as e:
            await ctx.send(f"Failed to delete role: {e}")
            return

    # Remove role from internal mapping and save
    del role_map[guild_id][internal_id]
    save_roles(role_map)
    await ctx.send(f"Internal mapping for ID `{internal_id}` has been removed.")


# ---------------- Simple test/joke commands ----------------
@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}")

@bot.command(name="commands")
async def show_commands(ctx):
    help_text = """
**Available Commands**

**Channel Auto-Delete**
`!enablechannel #channel` - Enable channel-wide auto-delete  
`!disablechannel #channel` - Disable channel auto-delete  
`!setwatchcount #channel <number>` - Set number of messages before deletion  

**User Watch**
`!addusertarget #channel @user` - Watch a specific user in a channel  
`!removeusertarget #channel @user` - Stop watching a specific user  

**Role Management**
`!addroles <id> <role name>` - Add a role to the assignable roles list  
`!roles` - Show all assignable roles and their IDs  
`!assign @user <id>` - Assign a role to a user by ID  
`!removeroles @user <id>` - Remove a role from a user by ID  

**Fun/Test**
`!hello` - Say hello  
`!defam @user` - A fun poke at a user  

"""
    await ctx.send(help_text)


@bot.command(name="defam")
async def defam(ctx, member: discord.Member):
    await ctx.send(f"{member.mention} is a potato")



# ---------------- Run Bot ----------------
bot.run(token, log_handler=handler, log_level=logging.DEBUG)
