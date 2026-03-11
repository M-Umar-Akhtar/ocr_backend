from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

Base = declarative_base()

class DocumentAnalysis(Base):
    __tablename__ = "document_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    passenger_name = Column(String, nullable=True)
    flight_number = Column(String, nullable=True)
    train_number = Column(String, nullable=True)
    travel_date = Column(DateTime, nullable=True)

    status = Column(String, nullable=False)  # approved | rejected | error

    error_message = Column(String, nullable=True)  # NEW COLUMN

    file_path = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)