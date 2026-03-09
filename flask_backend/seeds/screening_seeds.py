import random
from datetime import datetime

from faker import Faker

from flask_backend.models import Screening, ScreeningDate

DEFAULT_WIDTH = 325
DEFAULT_HEIGHT = (183, 488)
DEFAULT_PLACEHOLDER_IMG = "https://picsum.photos/{width}/{height}"


def create_screenings(db_session, placeholder_url: str | None = None):
    faker = Faker()
    placeholder_url = placeholder_url if placeholder_url else DEFAULT_PLACEHOLDER_IMG
    screenings = []
    for index in range(1, 8):
        image_height = random.choice(DEFAULT_HEIGHT)
        obj = Screening(
            movie_id=index,
            cinema_id=random.randint(1, 4),
            url=faker.uri(),
            image=faker.image_url(
                width=DEFAULT_WIDTH,
                height=image_height,
                placeholder_url=placeholder_url,
            ),
            image_width=DEFAULT_WIDTH,
            image_height=image_height,
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
