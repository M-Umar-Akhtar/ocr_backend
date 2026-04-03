from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

Base = declarative_base()

class DocumentAnalysis(Base):
    __tablename__ = "travel_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    passenger_name = Column(String(255), nullable=True)
    flight_number = Column(String(255), nullable=True)
    train_number = Column(String(255), nullable=True)
    travel_date = Column(DateTime, nullable=True)

    status = Column(String(30), nullable=False)  # approved | rejected | error

    error_message = Column(String(255), nullable=True) 

    file_path = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)