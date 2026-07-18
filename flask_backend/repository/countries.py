from flask_backend.db import db_session
from flask_backend.models import Country


def get_or_create_by_iso_code(iso_3166_1: str, name: str) -> Country:
    country = db_session.query(Country).filter(Country.iso_3166_1 == iso_3166_1).first()
    if country is None:
        country = Country(iso_3166_1=iso_3166_1, name=name)
        db_session.add(country)
        db_session.commit()
        db_session.refresh(country)
    return country
