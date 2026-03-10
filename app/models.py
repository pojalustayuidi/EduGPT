from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)


class MethodicEntry(Base):
    __tablename__ = "methodic_entries"

    id = Column(Integer, primary_key=True)
    author = Column(Text, nullable=True)
    source_title = Column(Text, nullable=True)
    methodic_text = Column(Text, nullable=True)

    qa_pairs = relationship("QAEntry", back_populates="methodic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MethodicEntry id={self.id} title={self.source_title}>"


class QAEntry(Base):
    __tablename__ = "qa_entries"

    id = Column(Integer, primary_key=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    methodic_id = Column(Integer, ForeignKey('methodic_entries.id'), nullable=True)

    methodic = relationship("MethodicEntry", back_populates="qa_pairs")

    def __repr__(self):
        return f"<QAEntry id={self.id} question={self.question[:50]}...>"
