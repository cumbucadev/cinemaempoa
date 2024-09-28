from datetime import datetime

from faker import Faker

from flask_backend.models import Screening, ScreeningDate


def create_screenings(db_session):
    faker = Faker()

    screenings = [
        Screening(
            movie_id=1,
            cinema_id=1,
            url=faker.uri(),
            # image=...,
            description=faker.text(),
            dates=[
                ScreeningDate(date=datetime.now().date(), time="11:00"),
                ScreeningDate(date=datetime.now().date(), time="13:00"),
                ScreeningDate(date=datetime.now().date(), time="17:00"),
            ],
        ),
        Screening(
            movie_id=2,
            cinema_id=1,
            url=faker.uri(),
            # image=..,
            description=faker.text(),
            dates=[
                ScreeningDate(date=datetime.now().date(), time="11:00"),
                ScreeningDate(date=datetime.now().date(), time="13:00"),
                ScreeningDate(date=datetime.now().date(), time="17:00"),
            ],
        ),
    ]

    db_session.add_all(screenings)
    db_session.commit()
