from typing import Optional

from flask_backend.import_json import ScrappedResult
from flask_backend.service.screening import import_scrapped_results


class Runner:
    def parse_scrapped_json(self, features):
        self.scrapped_results: ScrappedResult = ScrappedResult.from_jsonable(features)

    def import_scrapped_results(
        self, current_app, pipeline_run_id: Optional[int] = None
    ):
        return import_scrapped_results(
            self.scrapped_results, current_app, pipeline_run_id=pipeline_run_id
        )
