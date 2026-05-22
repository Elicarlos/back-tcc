from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Redacao(Base):
    __tablename__ = "redacoes"

    id = Column(Integer, primary_key=True, index=True)
    tema = Column(String, nullable=True)
    texto = Column(Text, nullable=False)
    data_criacao = Column(DateTime, default=datetime.utcnow)

    feedbacks = relationship("Feedback", back_populates="redacao", cascade="all, delete-orphan")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    redacao_id = Column(Integer, ForeignKey("redacoes.id", ondelete="CASCADE"), nullable=False)
    dados_correcao = Column(JSON, nullable=False)
    data_criacao = Column(DateTime, default=datetime.utcnow)

    redacao = relationship("Redacao", back_populates="feedbacks")


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="school")
    classrooms = relationship("Classroom", back_populates="school", cascade="all, delete-orphan")


class Classroom(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    school = relationship("School", back_populates="classrooms")
    users = relationship("User", back_populates="classroom")
    activities = relationship("Activity", back_populates="classroom", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="student", nullable=False)
    quota_limit = Column(Integer, default=20, nullable=False)
    quota_used = Column(Integer, default=0, nullable=False)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="SET NULL"), nullable=True)
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    school = relationship("School", back_populates="users")
    classroom = relationship("Classroom", back_populates="users")
    essays = relationship("Essay", back_populates="student", cascade="all, delete-orphan")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    theme = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime, nullable=True)
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    classroom = relationship("Classroom", back_populates="activities")
    creator = relationship("User")
    essays = relationship("Essay", back_populates="activity", cascade="all, delete-orphan")


class Essay(Base):
    __tablename__ = "essays"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True)
    theme = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    score_c1 = Column(Integer, default=0, nullable=False)
    score_c2 = Column(Integer, default=0, nullable=False)
    score_c3 = Column(Integer, default=0, nullable=False)
    score_c4 = Column(Integer, default=0, nullable=False)
    score_c5 = Column(Integer, default=0, nullable=False)
    score_total = Column(Integer, default=0, nullable=False)
    correction_json = Column(Text, nullable=True)
    teacher_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student = relationship("User", back_populates="essays")
    activity = relationship("Activity", back_populates="essays")


class Theme(Base):
    __tablename__ = "themes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, unique=True, index=True, nullable=False)
    source = Column(String, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

