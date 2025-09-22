from datetime import datetime

def validate_rating(rating: int):
    return 1 <= rating <= 5

def log_activity(action: str):
    with open("logs/activity.log", "a") as f:
        f.write(f"{datetime.now()} - {action}\n")
