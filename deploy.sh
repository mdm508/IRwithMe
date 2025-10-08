#!/bin/bash
rsync -avz --delete /path/to/your/project/ m@m:~/betty/
ssh m@m "cd ~/project && source venv/bin/activate && python3 bot.py"