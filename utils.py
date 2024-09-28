import json
from datetime import date, datetime


def get_formatted_day_str(date_str: str | None) -> str:
    """Returns the received date in format XX de XXXXX

    Args:
        date_str: date to convert [Optional]"""
    if date_str is None:
        # Get current date
        convert_date = datetime.now().date()
    else:
        convert_date = datetime.strptime(date_str, "%Y-%m-%d")

    day = convert_date.day
    month_number = convert_date.month
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


def string_is_day(date_string: str, compare_date_str: str) -> bool:
    """Checks whether a date string in the format

    24 de agosto | quinta-feira | 16h

    matches the received day in YYYY-MM-DD format."""
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
    compare_date = datetime.strptime(compare_date_str, "%Y-%m-%d").date()

    # Create a datetime object for the parsed date
    parsed_date = datetime(compare_date.year, month, day).date()

    # Check if the parsed date matches the comparison date
    return parsed_date == compare_date


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
