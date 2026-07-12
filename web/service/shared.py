"""Functions not bound to any specific database model"""

from datetime import date, timedelta
from typing import Tuple


def get_weekend_dates(current_date: date) -> Tuple[date, date, date]:
    # if we are on a weekend, we start from last friday
    # if we are on a weekday, we start from the next friday
    curr_weekday = current_date.weekday()
    friday_date = current_date + timedelta(days=4 - curr_weekday)
    saturday_date = friday_date + timedelta(days=1)
    sunday_date = friday_date + timedelta(days=2)
    return friday_date, saturday_date, sunday_date
