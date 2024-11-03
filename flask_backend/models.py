from typing import List

from sqlalchemy import JSON, Boolean, Column, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, relationship

from flask_backend.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = Column(Integer, primary_key=True)
    username: Mapped[str] = Column(String(20), unique=True, nullable=False)
    password: Mapped[str] = Column(String, nullable=False)
    roles: Mapped[List[str]] = Column(JSON, nullable=False)


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, index=True)

    screenings: Mapped[List["Screening"]] = relationship(back_populates="movie")


class Cinema(Base):
    __tablename__ = "cinemas"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)


class Screening(Base):
    __tablename__ = "screenings"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    cinema_id = Column(Integer, ForeignKey("cinemas.id"), nullable=False)
    url = Column(String, nullable=True)
    # TODO: should image and description belong to the movie?
    image = Column(String, nullable=True)
    image_alt = Column(String, nullable=True)
    description = Column(String, nullable=False)
    # TODO: maybe change this to a _status_ enum?
    draft = Column(Boolean, nullable=False, default=False)

    # TODO: maybe keep image related properties in a separate "medias" table?
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)

    movie: Mapped["Movie"] = relationship(back_populates="screenings")
    cinema: Mapped["Cinema"] = relationship()
    dates: Mapped[List["ScreeningDate"]] = relationship(back_populates="screening")


class ScreeningDate(Base):
    __tablename__ = "screening_dates"

    id = Column(Integer, primary_key=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(String, nullable=True)

    screening: Mapped["Screening"] = relationship(back_populates="dates")
