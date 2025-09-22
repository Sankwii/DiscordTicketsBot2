import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))
    TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID"))
    ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID"))
    DATABASE_URL = os.getenv("DATABASE_URL")