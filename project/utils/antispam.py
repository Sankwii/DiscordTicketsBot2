from datetime import datetime, timedelta
from utils.helpers import log_activity

class AntiSpamSystem:
    def __init__(self):
        self.users = {}

    def check_spam(self, user_id: str) -> bool:
        now = datetime.now()
        if user_id in self.users:
            last_request = self.users[user_id]
            if now - last_request < timedelta(minutes=5):
                return True
        self.users[user_id] = now
        return False

    def reset(self, user_id: str):
        if user_id in self.users:
            del self.users[user_id]

    def log_activity(self, user_id: str):
        """Делаем запись в общий лог через helpers.log_activity"""
        log_activity(f"AntiSpam check for user {user_id}")
