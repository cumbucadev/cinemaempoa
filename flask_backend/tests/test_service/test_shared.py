from datetime import datetime

from flask_backend.service.shared import parse_to_datetime_string


class TestParseTimeToDatetimeString:
    def test_parse_time_to_datetime_string(self):
        input_strs = [
            "\n\n\nHorários: 15:00h\n\n\n\nSala de Cinema\n\n",
            "\n\n\nHorários: 16:30h\n\n\n\nSala de Cinema\n\n",
            "\n\n\nHorários: 19:00h\n\n\n\nSala de Cinema\n\n",
            "14h45",
            "15h00",
            "16h45",
            "17h00",
            "17h15",
            "19h00",
            "15h15/ 19h30",
            "18h00",
            "19h00",
            "19h30",
            "13 de setembro | quarta-feira | 19h",
            "05 de setembro | terça-feira | 16h",
            "22 de setembro | segunda-feira | 16h\n22 de setembro | segunda-feira | 19h"
        ]
        expected_outputs = [  # noqa: E231
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T15:00"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T16:30"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T19:00"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T14:45"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T15:00"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T16:45"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T17:00"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T17:15"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T19:00"],
            [
                f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T15:15",
                f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T19:30",
            ],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T18:00"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T19:00"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T19:30"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T19:00"],
            [f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T16:00"],
            [
                f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T16:00",
                f"{datetime.strftime(datetime.now(), '%Y-%m-%d')}T19:00",
            ]

        ]
        for idx, input_str in enumerate(input_strs):
            expected_output = expected_outputs[idx]
            assert parse_to_datetime_string(input_str) == expected_output
