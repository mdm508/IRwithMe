"""Discord Reading Bot

Posts daily chunks of provided text to a channel. Commands allow loading text,
setting chunk size, starting the schedule, and skipping to the next chunk.

✅ General Permissions
	•	View Channels

✅ Text Permissions
	•	Send Messages
	•	Create Public Threads
	•	Create Private Threads
	•	Send Messages in Threads
	•	Manage Messages
	•	Pin Messages
	•	Manage Threads
	•	Embed Links
	•	Attach Files
	•	Read Message History
	•	Mention Everyone
	•	Add Reactions
	•	Use Slash Commands
	•	Create Polls

2815147051838528
"""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

import discord
from discord.ext import tasks
from discord.abc import Messageable

from config import load_token
from reading import (
    ChannelBookState,
    chunk_paragraphs,
    get_or_create_state,
    rebuild_chunks_from_existing,
    split_into_paragraphs,
)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

books: Dict[int, ChannelBookState] = {}

# Autocomplete functions
async def chunk_size_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[discord.app_commands.Choice[int]]:
    """Autocomplete for chunk size parameter."""
    common_sizes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 50]
    return [
        discord.app_commands.Choice(name=f"{size} paragraphs", value=size)
        for size in common_sizes
        if current.lower() in str(size).lower() or current == ""
    ][:25]

async def title_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[discord.app_commands.Choice[str]]:
    """Autocomplete for title parameter with common book titles."""
    common_titles = [
        "The Great Gatsby", "To Kill a Mockingbird", "1984", "Pride and Prejudice",
        "The Catcher in the Rye", "Lord of the Flies", "Animal Farm", "Brave New World",
        "The Hobbit", "Harry Potter", "The Chronicles of Narnia", "The Lord of the Rings",
        "Dune", "Foundation", "Neuromancer", "The Handmaid's Tale", "Beloved",
        "One Hundred Years of Solitude", "The Kite Runner", "Life of Pi"
    ]
    return [
        discord.app_commands.Choice(name=title, value=title)
        for title in common_titles
        if current.lower() in title.lower() or current == ""
    ][:25]

@tree.command(name="load", description="Load text into a new thread with required title")
@discord.app_commands.autocomplete(title=title_autocomplete)
async def load(
    interaction: discord.Interaction, 
    title: str,
    content: str
) -> None:
    """Load text into a new thread with required title."""
    if not title:
        await interaction.response.send_message("❌ Title cannot be empty", ephemeral=True)
        return
    
    if not content:
        await interaction.response.send_message("❌ Text content is required", ephemeral=True)
        return
    
    # Check if thread name already exists and make it unique
    thread_name = title
    counter = 1
    while any(channel.name == thread_name for channel in interaction.channel.threads):
        thread_name = f"{title} ({counter})"
        counter += 1
    
    # Create thread
    try:
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=1440  # 24 hours
        )
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to create threads in this channel", ephemeral=True)
        return
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to create thread: {str(e)}", ephemeral=True)
        return
    
    # Process text and store state
    paragraphs = split_into_paragraphs(content)
    default_chunk_size: int = 3
    chunks = chunk_paragraphs(paragraphs, default_chunk_size)
    books[thread.id] = ChannelBookState(
        chunks=chunks,
        index=0,
        chunk_size=default_chunk_size,
    )
    
    # Send confirmation in thread
    await thread.send(f"✅ **{thread_name}** loaded with {len(chunks)} chunks (size={default_chunk_size}).")
    
    # Send ephemeral confirmation (only visible to command user)
    await interaction.response.send_message(f"✅ Created thread **{thread_name}** with {len(chunks)} chunks!", ephemeral=True)

@tree.command(name="setchunksize", description="Set chunk size for this thread's loaded text (range 1–50)")
@discord.app_commands.autocomplete(size=chunk_size_autocomplete)
async def setChunkSize(
    interaction: discord.Interaction, 
    size: int
) -> None:
    """Set chunk size for this thread's loaded text (range 1–50)."""
    if interaction.channel.id not in books:
        await interaction.response.send_message("❌ No text loaded in this thread.", ephemeral=True)
        return
    data = books[interaction.channel.id]
    chunks = rebuild_chunks_from_existing(data.chunks, size)
    data.chunk_size, data.chunks, data.index = max(1, min(50, size)), chunks, 0
    await interaction.response.send_message(f"📖 Chunk size set to {data.chunk_size}. Restarting from beginning.")

@tree.command(name="start", description="Start daily delivery of chunks to this thread")
async def start(interaction: discord.Interaction) -> None:
    """Start daily delivery of chunks to this thread."""
    if interaction.channel.id not in books:
        await interaction.response.send_message("❌ No text loaded in this thread.", ephemeral=True)
        return
    # Start the task loop for this thread
    post_chunks.start(interaction.channel)
    await interaction.response.send_message("🚀 Daily reading started!")

@tree.command(name="more", description="Send the next chunk_size number of chunks immediately")
async def more(interaction: discord.Interaction) -> None:
    """Send the next chunk_size number of chunks immediately to this thread."""
    if interaction.channel.id not in books:
        await interaction.response.send_message("❌ No text loaded in this thread.", ephemeral=True)
        return
    
    data = books[interaction.channel.id]
    chunk_size = data.chunk_size
    
    await interaction.response.defer()
    
    # Send multiple chunks based on chunk_size
    chunks_sent = 0
    for _ in range(chunk_size):
        result = await send_next_chunk(interaction.channel)
        if result is None:  # No more chunks available
            break
        chunks_sent += 1
    
    if chunks_sent == 0:
        await interaction.followup.send("🎉 All chunks have been sent!", ephemeral=True)
    else:
        await interaction.followup.send(f"📚 Sent {chunks_sent} chunk(s)!", ephemeral=True)

@tree.command(name="ping", description="Test if the bot is responding")
async def ping(interaction: discord.Interaction) -> None:
    """Test command to verify bot is working."""
    await interaction.response.send_message("🏓 Pong! Bot is working!", ephemeral=True)

@tree.command(name="help", description="Show available commands and usage")
async def help_command(interaction: discord.Interaction) -> None:
    """Show help information for all available commands."""
    help_text = """
📚 **Discord Reading Bot Commands**

**Main Commands:**
• `/ping` - Test if the bot is responding
• `/load` - Load text into a new thread (title and content required)
• `/setchunksize` - Set paragraphs per chunk (1-50) in current thread
• `/start` - Begin daily posts in current thread  
• `/more` - Send next chunk_size number of chunks immediately
• `/help` - Show this help message

**How to Use:**
1. Use `/load` in any channel to create a reading thread
2. Go into the created thread to use other commands
3. Use `/start` to begin daily chunk delivery
4. Use `/more` to get the next chunk_size chunks immediately

**Notes:**
• Each text gets its own dedicated thread
• Chunk size defaults to 3 paragraphs
• Threads auto-archive after 24 hours of inactivity
• All commands except `/load` work only in reading threads
"""
    await interaction.response.send_message(help_text, ephemeral=True)

async def send_next_chunk(channel: Messageable) -> Optional[discord.Message]:
    """Send the next chunk for the given thread, advancing progress.

    Returns the sent message, or None if all chunks are delivered or no state.
    """
    channel_id_attr = getattr(channel, "id", None)
    if channel_id_attr is None or channel_id_attr not in books:
        return None
    data = books[channel_id_attr]
    if data.index >= len(data.chunks):
        return await channel.send("🎉 All chunks sent!")
    chunk = data.chunks[data.index]
    msg = await channel.send(f"📚 **Chunk {data.index + 1}:**\n\n{chunk}")
    data.index += 1
    return msg

@tasks.loop(hours=24)
async def post_chunks(channel: Messageable) -> None:
    """Task loop handler: post the next chunk every 24 hours for a thread."""
    channel_id_attr = getattr(channel, "id", None)
    if channel_id_attr in books:
        await send_next_chunk(channel)

@client.event
async def on_ready():
    """Sync slash commands when bot is ready."""
    print(f"Bot logged in as {client.user}")
    print(f"Bot is in {len(client.guilds)} guilds")
    
    try:
        # Sync commands globally (this can take up to 1 hour to propagate)
        synced = await tree.sync()
        print(f"Synced {len(synced)} command(s) globally")
        print("Bot is ready!")
        print("Note: Global commands may take up to 1 hour to appear")
        
        # Also sync to each guild for immediate availability
        for guild in client.guilds:
            try:
                guild_synced = await tree.sync(guild=guild)
                print(f"Synced {len(guild_synced)} commands to {guild.name}")
            except Exception as e:
                print(f"Failed to sync to {guild.name}: {e}")
                
    except Exception as e:
        print(f"Failed to sync commands: {e}")
        print("Commands may take up to 1 hour to appear globally")

def main() -> None:
    """Entrypoint to run the bot."""
    token = load_token()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set in environment.")
    client.run(token)


if __name__ == "__main__":
    main()



