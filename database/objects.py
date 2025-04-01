from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

base = declarative_base()

engine = create_engine("sqlite:///database.db")

DBsession = sessionmaker(bind=engine)
session = DBsession()
