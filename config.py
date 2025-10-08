from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv


def load_token() -> Optional[str]:
    """Load the Discord bot token from environment variables.

    Returns None if the token is not present.
    """
    load_dotenv()
    return os.getenv("DISCORD_TOKEN")



