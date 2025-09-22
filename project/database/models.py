from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Ticket(Base):
    """Модель для хранения тикетов"""
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), nullable=False)
    content = Column(String(1000), nullable=False)
    status = Column(String(20), default="open")
    created_at = Column(DateTime)
    closed_at = Column(DateTime)
    tag = Column(String(20))
    
    feedback = relationship("Feedback", back_populates="ticket", uselist=False)

class Feedback(Base):
    """Модель для хранения отзывов"""
    __tablename__ = "feedbacks"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(String(500))
    created_at = Column(DateTime)
    
    ticket_id = Column(Integer, ForeignKey('tickets.id'), nullable=False)
    ticket = relationship("Ticket", back_populates="feedback")

class Tag(Base):
    """Модель для тегов тикетов"""
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)
    emoji = Column(String(5), nullable=False)
    description = Column(String(100))

    def __repr__(self):
        return f"{self.emoji} {self.name}"
