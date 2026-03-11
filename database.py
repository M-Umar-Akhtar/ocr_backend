from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, echo=True)  # echo=True helps debug SQL
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables if they do not exist
Base.metadata.create_all(bind=engine)