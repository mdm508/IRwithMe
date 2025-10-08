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

import datetime as dt
import textwrap
from typing import Dict, List, Optional

import discord
from discord.ext import tasks
from discord.abc import Messageable

from config import load_token
from reading import (
    ChannelBookState,
    chunk_paragraphs,
    rebuild_chunks_from_existing,
    split_into_paragraphs,
)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

books: Dict[int, ChannelBookState] = {}

async def create_reading_thread(
    interaction: discord.Interaction,
    title: str,
    content: str,
    *,
    default_chunk_size: int = 3
) -> None:
    """Create a reading thread with provided content and store initial state."""
    if not title:
        await interaction.response.send_message("❌ Title cannot be empty", ephemeral=True)
        return

    if not content or not content.strip():
        await interaction.response.send_message("❌ Text content is required", ephemeral=True)
        return

    thread_name = title
    counter = 1
    current_channel_threads = getattr(interaction.channel, "threads", [])
    while any(channel.name == thread_name for channel in current_channel_threads):
        thread_name = f"{title} ({counter})"
        counter += 1

    try:
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=1440,
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to create threads in this channel", ephemeral=True
        )
        return
    except Exception as exc:
        await interaction.response.send_message(f"❌ Failed to create thread: {exc}", ephemeral=True)
        return

    paragraphs = split_into_paragraphs(content)
    chunks = chunk_paragraphs(paragraphs, default_chunk_size)
    books[thread.id] = ChannelBookState(
        chunks=chunks,
        index=0,
        chunk_size=default_chunk_size,
    )

    await thread.send(
        f"✅ **{thread_name}** loaded with {len(chunks)} chunks (size={default_chunk_size}). "
        "Use `/join` in this thread so your reactions count toward auto-advance."
    )
    await interaction.response.send_message(
        f"✅ Created thread **{thread_name}** with {len(chunks)} chunks!", ephemeral=True
    )

DISCORD_MESSAGE_LIMIT = 2000
CHUNK_WRAP_WIDTH = 1900


def format_chunk_messages(index: int, chunk: str) -> List[str]:
    """Render a chunk as one or more Discord blockquote messages under the limit."""

    def header(part: int) -> List[str]:
        suffix = "" if part == 0 else f" (continued {part})"
        return [f"> *chunk {index + 1}{suffix}*", ">"]

    def split_line(text: str) -> List[str]:
        if not text:
            return [""]
        return textwrap.wrap(
            text,
            width=CHUNK_WRAP_WIDTH,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]

    segments: List[str] = []
    for raw_line in chunk.splitlines():
        segments.extend(split_line(raw_line))

    if not segments:
        segments = [""]

    messages: List[str] = []
    part_index = 0
    current_lines = header(part_index)

    for segment in segments:
        quoted_line = f"> {segment}" if segment else "> "
        candidate = "\n".join(current_lines + [quoted_line])
        if len(candidate) > DISCORD_MESSAGE_LIMIT:
            messages.append("\n".join(current_lines))
            part_index += 1
            current_lines = header(part_index)
            candidate = "\n".join(current_lines + [quoted_line])
            if len(candidate) > DISCORD_MESSAGE_LIMIT:
                # fallback: split the segment further to fit with header
                fallback_width = max(1, DISCORD_MESSAGE_LIMIT - len("\n".join(header(part_index))) - 5)
                sub_segments = [
                    segment[i:i + fallback_width] for i in range(0, len(segment), fallback_width)
                ]
                for sub in sub_segments:
                    quoted_sub_line = f"> {sub}" if sub else "> "
                    candidate_sub = "\n".join(current_lines + [quoted_sub_line])
                    if len(candidate_sub) > DISCORD_MESSAGE_LIMIT:
                        messages.append("\n".join(current_lines))
                        part_index += 1
                        current_lines = header(part_index)
                    current_lines.append(quoted_sub_line)
                continue
        current_lines.append(quoted_line)

    messages.append("\n".join(current_lines))
    return messages

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
    await create_reading_thread(interaction, title, content)

@tree.command(name="loadfile", description="Load text into a new thread from an uploaded .txt file")
@discord.app_commands.autocomplete(title=title_autocomplete)
async def loadfile(
    interaction: discord.Interaction,
    title: str,
    file: discord.Attachment
) -> None:
    """Load text into a new thread using contents of an attached text file."""
    if file is None:
        await interaction.response.send_message("❌ Please attach a .txt file.", ephemeral=True)
        return

    if not file.filename.lower().endswith(".txt"):
        await interaction.response.send_message("❌ Only .txt files are supported.", ephemeral=True)
        return

    try:
        file_bytes = await file.read()
    except Exception as exc:
        await interaction.response.send_message(f"❌ Couldn't read the file: {exc}", ephemeral=True)
        return

    try:
        text_content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        await interaction.response.send_message(
            "❌ Failed to decode file. Please upload UTF-8 encoded text.", ephemeral=True
        )
        return

    await create_reading_thread(interaction, title, text_content)

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
    normalized_size = max(1, min(50, size))
    chunks = rebuild_chunks_from_existing(data.chunks, normalized_size)
    previous_index = data.index

    data.chunk_size = normalized_size
    data.chunks = chunks
    data.index = min(previous_index, len(chunks))
    data.completed = data.index >= len(chunks)

    if data.completed:
        message = f"📖 Chunk size set to {data.chunk_size}. All chunks already delivered."
    else:
        message = (
            f"📖 Chunk size set to {data.chunk_size}. Continuing from chunk {data.index + 1}."
        )

    await interaction.response.send_message(message)

@tree.command(name="start", description="Start daily delivery of chunks to this thread")
async def start(interaction: discord.Interaction) -> None:
    """Start daily delivery of chunks to this thread."""
    if interaction.channel.id not in books:
        await interaction.response.send_message("❌ No text loaded in this thread.", ephemeral=True)
        return
    data = books[interaction.channel.id]
    now = dt.datetime.now()
    data.auto_active = True

    if data.auto_post_time is None:
        data.auto_post_time = now.time().replace(second=0, microsecond=0)
        data.last_auto_post_date = now.date()
        next_time = data.auto_post_time.strftime("%H:%M")
        message = (
            f"🚀 Daily reading started! Next chunk will post daily at {next_time} (first run tomorrow)."
        )
    else:
        scheduled_today = now.replace(
            hour=data.auto_post_time.hour,
            minute=data.auto_post_time.minute,
            second=0,
            microsecond=0,
        )
        if scheduled_today <= now:
            data.last_auto_post_date = now.date()
            suffix = "starting tomorrow"
        else:
            data.last_auto_post_date = None
            suffix = "starting later today"
        message = (
            f"🚀 Daily reading started! Next chunk will post daily at "
            f"{data.auto_post_time.strftime('%H:%M')} ({suffix})."
        )

    await interaction.response.send_message(message)

@tree.command(name="settime", description="Set the daily auto chunk time (HH:MM, 24-hour).")
async def set_time(interaction: discord.Interaction, time: str) -> None:
    """Set the daily auto chunk delivery time for this thread."""
    if interaction.channel.id not in books:
        await interaction.response.send_message("❌ No text loaded in this thread.", ephemeral=True)
        return

    try:
        parsed_time = dt.datetime.strptime(time, "%H:%M").time()
    except ValueError:
        await interaction.response.send_message("❌ Time must be in HH:MM format (24-hour).", ephemeral=True)
        return

    data = books[interaction.channel.id]
    data.auto_post_time = parsed_time
    now = dt.datetime.now()
    descriptor = "ready to start when you run `/start`"

    if data.auto_active:
        scheduled_today = now.replace(
            hour=parsed_time.hour,
            minute=parsed_time.minute,
            second=0,
            microsecond=0,
        )
        if scheduled_today <= now:
            data.last_auto_post_date = now.date()
            descriptor = "next post will be tomorrow"
        else:
            data.last_auto_post_date = None
            descriptor = "next post will be later today"

    await interaction.response.send_message(
        f"⏰ Daily auto time set to {parsed_time.strftime('%H:%M')} — {descriptor}."
    )

@tree.command(name="join", description="Join the reaction-based auto advance for this thread")
async def join_command(interaction: discord.Interaction) -> None:
    """Register a member so their reactions count toward auto-advancing chunks."""
    channel_id = getattr(interaction.channel, "id", None)
    if channel_id not in books:
        await interaction.response.send_message("❌ No reading session is active in this thread.", ephemeral=True)
        return

    data = books[channel_id]
    user_id = interaction.user.id

    if user_id in data.joined_users:
        await interaction.response.send_message(
            "👋 You're already in! React to the latest chunk when you finish reading.", ephemeral=True
        )
        return

    data.joined_users.add(user_id)
    data.latest_reactors.discard(user_id)

    await interaction.response.send_message(
        f"✅ Added you to the reading roster. {len(data.joined_users)} member(s) are now tracking reactions.",
        ephemeral=True,
    )

@tree.command(name="jump", description="Jump to a specific chunk number and deliver it")
async def jump_command(interaction: discord.Interaction, chunk: int) -> None:
    """Jump to a specific chunk and send it immediately."""
    channel_id = getattr(interaction.channel, "id", None)
    if channel_id not in books:
        await interaction.response.send_message("❌ No reading session is active in this thread.", ephemeral=True)
        return

    data = books[channel_id]
    total_chunks = len(data.chunks)

    if total_chunks == 0:
        await interaction.response.send_message("❌ No chunks are loaded for this thread.", ephemeral=True)
        return

    if chunk < 1 or chunk > total_chunks:
        await interaction.response.send_message(
            f"❌ Chunk must be between 1 and {total_chunks}.", ephemeral=True
        )
        return

    data.index = max(0, chunk - 1)
    data.completed = False

    last_message = await deliver_chunk(interaction.channel, data, data.index)
    if last_message is None:
        await interaction.response.send_message("⚠️ Failed to send the requested chunk.", ephemeral=True)
        return

    data.index = chunk
    data.completed = data.index >= total_chunks

    await interaction.response.send_message(
        f"⏭️ Jumped to chunk {chunk}. Next chunk will be {data.index + 1}" if not data.completed else
        f"⏭️ Jumped to chunk {chunk}. All chunks have now been delivered.",
        ephemeral=True,
    )

@tree.command(name="again", description="Resend the most recently delivered chunk")
async def again_command(interaction: discord.Interaction) -> None:
    """Resend the last delivered chunk without changing progress."""
    channel_id = getattr(interaction.channel, "id", None)
    if channel_id not in books:
        await interaction.response.send_message("❌ No reading session is active in this thread.", ephemeral=True)
        return

    data = books[channel_id]
    if not data.chunks or data.index == 0:
        await interaction.response.send_message("ℹ️ No chunks have been delivered yet.", ephemeral=True)
        return

    last_chunk_index = min(data.index, len(data.chunks)) - 1
    last_message = await deliver_chunk(interaction.channel, data, last_chunk_index)
    if last_message is None:
        await interaction.response.send_message("⚠️ Failed to resend the previous chunk.", ephemeral=True)
        return

    await interaction.response.send_message(
        f"🔁 Resent chunk {last_chunk_index + 1}. React again when you're ready for the next chunk.",
        ephemeral=True,
    )

@tree.command(name="info", description="Show reading progress details for this thread")
async def info_command(interaction: discord.Interaction) -> None:
    """Provide a summary of reading progress and scheduling details."""
    channel_id = getattr(interaction.channel, "id", None)
    if channel_id not in books:
        await interaction.response.send_message("❌ No reading session is active in this thread.", ephemeral=True)
        return

    data = books[channel_id]
    total_chunks = len(data.chunks)
    next_chunk = data.index + 1 if data.index < total_chunks else None
    last_chunk = data.index if data.index > 0 else None
    remaining = max(0, total_chunks - data.index)
    joined = len(data.joined_users)
    awaiting = max(0, joined - len(data.latest_reactors)) if data.latest_message_id else joined

    auto_status = "inactive"
    if data.auto_active and data.auto_post_time:
        auto_status = f"active daily at {data.auto_post_time.strftime('%H:%M')}"
    elif data.auto_active:
        auto_status = "active (time not set)"

    info_lines = [
        f"• Total chunks: {total_chunks}",
        f"• Last chunk sent: {last_chunk if last_chunk else 'none yet'}",
        f"• Next chunk: {next_chunk if next_chunk else '✅ completed'}",
        f"• Chunks remaining: {remaining}",
        f"• Chunk size: {data.chunk_size}",
        f"• Auto posting: {auto_status}",
        f"• Joined readers: {joined}",
    ]

    if data.joined_users:
        info_lines.append(f"• Awaiting reactions: {awaiting}")

    await interaction.response.send_message("\n".join(info_lines), ephemeral=True)

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
    chunks_sent = await send_chunk_batch(interaction.channel, chunk_size)
    
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
• `/loadfile` - Load text into a new thread from a .txt file
• `/setchunksize` - Set paragraphs per chunk (1-50) in current thread
• `/start` - Begin daily posts in current thread  
• `/settime` - Set daily delivery time (HH:MM, 24-hour) for this thread
• `/join` - Opt-in so your reactions count toward auto-advance
• `/jump` - Jump to a specific chunk number immediately
• `/again` - Resend the most recent chunk
• `/info` - Show reading progress and schedule
• `/more` - Send next chunk_size number of chunks immediately
• `/help` - Show this help message

**How to Use:**
1. Use `/load` in any channel to create a reading thread
2. Go into the created thread to use other commands
3. Use `/join` if you want your reactions to count toward advancing
4. Use `/settime` to choose a delivery time (optional)
5. Use `/start` to begin daily chunk delivery
6. Use `/jump` or `/again` as needed to revisit chunks
7. Use `/more` to get the next chunk_size chunks immediately

**Notes:**
• Each text gets its own dedicated thread
• Chunk size defaults to 3 paragraphs
• Threads auto-archive after 24 hours of inactivity
• All commands except `/load` work only in reading threads
• Only members who run `/join` are counted for auto-advance reactions
• When all joined members react to the newest chunk, the next chunk will post automatically
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
    if data.completed:
        return None
    if data.index >= len(data.chunks):
        data.completed = True
        data.latest_message_id = None
        data.latest_reactors.clear()
        await channel.send("🎉 All chunks sent!")
        return None
    last_message = await deliver_chunk(channel, data, data.index)
    data.index += 1
    data.completed = data.index >= len(data.chunks)
    return last_message


async def send_chunk_batch(channel: Messageable, batch_size: int) -> int:
    """Send up to batch_size chunks to the given channel."""
    if batch_size <= 0:
        return 0

    sent = 0
    for _ in range(batch_size):
        result = await send_next_chunk(channel)
        if result is None:
            break
        sent += 1
    return sent


async def deliver_chunk(
    channel: Messageable,
    data: ChannelBookState,
    chunk_index: int
) -> Optional[discord.Message]:
    """Deliver a specific chunk without mutating the index."""
    if chunk_index < 0 or chunk_index >= len(data.chunks):
        return None

    chunk = data.chunks[chunk_index]
    formatted_messages = format_chunk_messages(chunk_index, chunk)
    last_message: Optional[discord.Message] = None

    for formatted_chunk in formatted_messages:
        last_message = await channel.send(formatted_chunk)

    if last_message:
        data.latest_message_id = last_message.id
    else:
        data.latest_message_id = None
    data.latest_reactors.clear()
    return last_message

@tasks.loop(seconds=60)
async def check_scheduled_posts() -> None:
    """Poll active threads and post chunks at their scheduled time."""
    now = dt.datetime.now()
    current_date = now.date()
    current_hour = now.hour
    current_minute = now.minute

    for channel_id, data in books.items():
        if (
            not data.auto_active
            or data.auto_post_time is None
            or data.completed
            or data.last_auto_post_date == current_date
        ):
            continue

        if (
            data.auto_post_time.hour == current_hour
            and data.auto_post_time.minute == current_minute
        ):
            channel = client.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await client.fetch_channel(channel_id)
                except Exception:
                    continue

            await send_next_chunk(channel)
            data.last_auto_post_date = current_date

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
    """Auto-advance chunks when all reacting members acknowledge the latest post."""
    if payload.user_id == getattr(client.user, "id", None):
        return

    if payload.channel_id not in books:
        return

    data = books[payload.channel_id]

    if payload.member and payload.member.bot:
        return

    if data.completed or data.latest_message_id != payload.message_id:
        return

    if payload.user_id not in data.joined_users:
        return

    data.latest_reactors.add(payload.user_id)

    if data.joined_users and data.joined_users.issubset(data.latest_reactors):
        channel = client.get_channel(payload.channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(payload.channel_id)
            except Exception:
                return
        await send_chunk_batch(channel, data.chunk_size)

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
        if not check_scheduled_posts.is_running():
            check_scheduled_posts.start()

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
