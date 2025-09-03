"""Functions not bound to any specific database model"""

import re
from datetime import datetime
from typing import List, Optional


def parse_to_datetime_string(time_str: List[str] | str) -> Optional[List[str]]:
    """Receives string in format:
    - ["2025-08-08T14:30", "2025-08-10T14:30", "2025-08-13T14:30"]
    - \\n\\n\\nHorários: 12:00h\\n\\n\\n\\nSala de Cinema\\n\\n
    - 16h
    - 15h30/ 19h30
    - 15h/ 19h
    - 15h15
    - 13 de setembro | quarta-feira | 19h
    - 05 de setembro | terça-feira | 16h30

    Attempts to parse it into a list of strings in format:
    - ["2023-11-11T12:00"]"""
    if isinstance(time_str, list):
        # assume the strings are in the correct format
        # TODO: check that each individual list item is correctly parsed
        return time_str

    today_date = datetime.strftime(datetime.now(), "%Y-%m-%d")
    if time_str is None or time_str == "":
        return []

    if time_str.startswith("\n\n\nHorários: "):
        stripped_time = time_str.strip("\n\n\nHorários: ").split("h")
        return [f"{today_date}T{stripped_time[0]}"]

    # check if time_str is in format DD de MMMM | dia-da-semana | HHhMM,
    # and save the match to a variable
    format_match = re.match(
        r"^\d{1,2} de \w+ \| [\w-]+ \| (\d{1,2}h?(?:\d{1,2})?)$", time_str
    )
    if format_match:
        split_match = format_match.group(1).split("h")
        if len(split_match) == 1 or split_match[1] == "":
            return [f"{today_date}T{split_match[0]}:00"]
        return [f"{today_date}T{split_match[0]}:{split_match[1]}"]

    # check if time_str is in format HHhMM using regex
    if re.match(r"^\d{1,2}h\d{1,2}$", time_str):
        return [f"{today_date}T{time_str[0:2]}:{time_str[-2:]}"]

    if "/" in time_str:
        split_time = time_str.split("/")
        formatted_time = []
        for time in split_time:
            if time.strip().endswith("h"):
                formatted_time.append(f"{today_date}T{time.strip()[:-1]}:00")
            else:
                hour_mins = time.strip().split("h")
                formatted_time.append(f"{today_date}T{hour_mins[0]}:{hour_mins[1]}")

        return formatted_time

    if time_str.strip().endswith("h"):
        return [f"{today_date}T{time_str[:-1]}:00"]

    return None
