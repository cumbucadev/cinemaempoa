from dataclasses import dataclass
from typing import List, Optional

from flask_backend.service.shared import parse_to_datetime_string


@dataclass
class ScrappedFeature:
    poster: Optional[str]
    time: Optional[str]
    title: str
    original_title: Optional[str]
    price: Optional[str]
    director: Optional[str]
    classification: Optional[str]
    general_info: Optional[str]
    excerpt: str
    read_more: Optional[str]

    @classmethod
    def from_jsonable(cls, feature_json: str):
        received_time = feature_json.get("time", None)
        if received_time is not None:
            formatted_time_strs = parse_to_datetime_string(received_time)
        else:
            formatted_time_strs = None

        return cls(
            poster=feature_json.get("poster", None),
            time=formatted_time_strs,
            title=feature_json["title"],
            original_title=feature_json.get("original_title", None),
            price=feature_json.get("price", None),
            director=feature_json.get("director", None),
            classification=feature_json.get("classification", None),
            general_info=feature_json.get("general_info", None),
            excerpt=feature_json["excerpt"],
            read_more=feature_json.get("read_more", None),
        )


@dataclass
class ScrappedCinema:
    url: str
    cinema: str
    slug: str
    features: List[ScrappedFeature]

    @classmethod
    def from_jsonable(cls, cinema_json: str):
        return cls(
            url=cinema_json["url"],
            cinema=cinema_json["cinema"],
            slug=cinema_json["slug"],
            features=[
                ScrappedFeature.from_jsonable(features_json)
                for features_json in cinema_json["features"]
            ],
        )


@dataclass
class ScrappedResult:
    """Handles the structure of scrapping results."""

    cinemas: List[ScrappedCinema]

    @classmethod
    def from_jsonable(cls, scrapped_results: str):
        return cls(
            cinemas=[ScrappedCinema.from_jsonable(cinema) for cinema in scrapped_results]
        )
