import random
from datetime import datetime

from faker import Faker

from flask_backend.models import Screening, ScreeningDate

DEFAULT_WIDTH=303
DEFAULT_HEIGHT=455


def create_screenings(db_session):
    faker = Faker()
    screenings = []
    for index in range(1, 8):
        
        obj = Screening(
            movie_id=index,
            cinema_id=random.randint(1, 4),
            url=faker.uri(),
            image=faker.image_url(DEFAULT_WIDTH, DEFAULT_HEIGHT),
            image_width=DEFAULT_WIDTH,
            image_height=DEFAULT_HEIGHT,
            description=faker.text(),
            dates=[
                ScreeningDate(date=datetime.now().date(), time="11:00"),
                ScreeningDate(date=datetime.now().date(), time="13:00"),
                ScreeningDate(date=datetime.now().date(), time="17:00"),
            ],
        )
        
        screenings.append(obj)
       

    db_session.add_all(screenings)
    db_session.commit()
