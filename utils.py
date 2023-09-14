import json

from datetime import date, datetime


def get_formatted_day_str() -> str:
    """Returns the current day in format XX de XXXXX"""
    # Get current date
    current_date = datetime.now().date()
    day = current_date.day
    month_number = current_date.month
    # Convert month name to month number
    month_mapping = {
        1: "janeiro",
        2: "fevereiro",
        3: "março",
        4: "abril",
        5: "maio",
        6: "junho",
        7: "julho",
        8: "agosto",
        9: "setembro",
        10: "outubro",
        11: "novembro",
        12: "dezembro",
    }
    month_name = month_mapping[month_number]
    return f"{day} de {month_name}"


def string_is_current_day(date_string: str) -> bool:
    """Checks whether a date string in the format

    24 de agosto | quinta-feira | 16h

    matches the current day."""
    # Convert month name to month number
    month_mapping = {
        "janeiro": 1,
        "fevereiro": 2,
        "março": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    }

    # Extract day, month, and time
    day_month, week_day, time = date_string.split(" | ")
    day_month_split = day_month.split()
    day = int(day_month_split[0])
    month = month_mapping[day_month_split[-1]]

    # Get current date
    current_date = datetime.now().date()

    # Create a datetime object for the parsed date
    parsed_date = datetime(current_date.year, month, day).date()

    # Check if the parsed date is the current date
    return parsed_date == current_date


def is_monday():
    return date.today().weekday() == 0


def dump_utf8_json(jsonable_object) -> str:
    """Returns a json string while keeping utf8 artifacts such as accents, etc.
    Adapted from https://stackoverflow.com/a/18337754/14427854"""
    return json.dumps(jsonable_object, ensure_ascii=False).encode("utf8").decode()
