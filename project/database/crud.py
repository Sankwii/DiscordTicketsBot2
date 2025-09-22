from sqlalchemy.orm import Session
from sqlalchemy import func
from .models import Ticket, Feedback
from datetime import datetime

def get_statistics(db: Session):
    """Возвращает статистику по тикетам и отзывам"""
    stats = {
        "total_tickets": db.query(Ticket).count(),
        "open_tickets": db.query(Ticket).filter(Ticket.status == "open").count(),
        "avg_rating": db.query(func.avg(Feedback.rating)).scalar() or 0.0
    }
    return stats

def create_ticket(db: Session, user_id: str, content: str, tag: str):
    new_ticket = Ticket(
        user_id=user_id,
        content=content,
        tag=tag,
        created_at=datetime.now()
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    return new_ticket

def close_ticket(db: Session, ticket_id: int):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket:
        ticket.status = "closed"
        ticket.closed_at = datetime.now()
        db.commit()
    return ticket

def create_feedback(db: Session, user_id: str, rating: int, ticket_id: int, comment: str = None):
    """
    Привязывает отзыв к конкретному тикету. 
    Если отзыв уже есть для этого ticket_id, возвращает None.
    """
    existing = db.query(Feedback).filter(Feedback.ticket_id == ticket_id).first()
    if existing:
        return None

    feedback = Feedback(
        user_id=user_id,
        rating=rating,
        comment=comment,
        created_at=datetime.now(),
        ticket_id=ticket_id
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
