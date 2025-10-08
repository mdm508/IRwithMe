## Discord Reading Bot – MVP

Posts one chunk of text per day into a Discord thread. Load text with a required title, creates a new thread for each book, auto-deletes load commands, and provides chunk management within threads.

### Prerequisites
- Python 3.9+
- Discord bot token (create in Developer Portal)
- Git

### Setup
```bash
python3 -m venv venv
source venv/bin/activate       # Mac/Linux
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Create a `.env` file in the project root:
```
DISCORD_TOKEN=your-bot-token-here
```

### Run
```bash
source venv/bin/activate
python bot.py
```

### Commands
- `/load title:"Book Title" content:"Your text here..."` – load text into a new thread (title required)
- `/setchunksize size:5` – set paragraphs per chunk (1–50) in current thread
- `/start` – begin daily posts in current thread
- `/more` – send next chunk_size chunks immediately in current thread
- `/help` – show available commands and usage

**Note:** All commands except `/load` must be used within the thread created for that text.

### Project Structure
```
.
├── bot.py
├── reading.py
├── config.py
├── requirements.txt
├── .gitignore
└── .env  # not committed
```

### Notes
- This MVP stores per-thread state in-memory. Restarting the bot resets progress.
- Load commands are auto-deleted to keep channels clean (with ephemeral confirmation).
- Each text creates a separate thread for organized reading.
- Future ideas: EPUB parsing, reactions, reminders, per-user progress, stats.



