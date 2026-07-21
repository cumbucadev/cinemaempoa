import json

from flask import Blueprint, abort, render_template, request, url_for
from werkzeug.routing import BuildError

from flask_backend.repository import pipeline_runs
from flask_backend.repository.alerts import get_by_pipeline_run_id as get_alerts_by_run
from flask_backend.repository.movie_metadata_fetch_attempts import (
    get_by_pipeline_run_id as get_metadata_attempts_by_run,
)
from flask_backend.repository.poster_fetch_attempts import (
    get_by_pipeline_run_id as get_poster_attempts_by_run,
)
from flask_backend.repository.screenings import (
    get_by_pipeline_run_id as get_screenings_by_run,
)
from flask_backend.routes.auth import login_required

bp = Blueprint("admin_pipelines", __name__)

# Each entry is one health row on /admin/pipelines. import-json shares one
# CLI command across three cinema groups that run on very different
# schedules (see docs/superpowers/specs/2026-07-21-admin-pipeline-dashboard-design.md),
# so it needs three separate groups here rather than one. The `source`
# value must stay in sync with flask_backend/commands.py::_run_import_json,
# which builds it as sorted(cinema_slugs) joined with ",".
PIPELINE_GROUPS = [
    {
        "pipeline_name": "import-json",
        "source": "capitolio,paulo-amorim,sala-redencao",
        "label": "Importação — Capitólio, Paulo Amorim, Sala Redenção",
    },
    {
        "pipeline_name": "import-json",
        "source": "cinebancarios",
        "label": "Importação — CineBancários",
    },
    {
        "pipeline_name": "import-json",
        "source": "cine-cinco",
        "label": "Importação — Cine Cinco",
    },
    {
        "pipeline_name": "fetch-posters",
        "source": None,
        "label": "Busca de Posters",
    },
    {
        "pipeline_name": "fetch-movie-metadata",
        "source": None,
        "label": "Busca de Metadados de Filmes",
    },
    {
        "pipeline_name": "generate-alerts",
        "source": None,
        "label": "Geração de Alertas",
    },
]


def _group_label(pipeline_name, source):
    for group in PIPELINE_GROUPS:
        if group["pipeline_name"] == pipeline_name and group["source"] == source:
            return group["label"]
    return pipeline_name


def _detail_url(run):
    """Link to the Task 7 detail page, or None if it doesn't exist yet.

    Task 7 adds the `admin_pipelines.detail` endpoint. Until it lands,
    `url_for` would raise BuildError on every history render (not just on
    click), so this guards it and lets the template fall back to plain
    text.
    """
    try:
        return url_for(
            "admin_pipelines.detail", pipeline_name=run.pipeline_name, run_id=run.id
        )
    except BuildError:
        return None


@bp.route("/admin/pipelines")
@login_required
def index():
    """Health overview: latest run per tracked pipeline/source group."""
    rows = []
    for group in PIPELINE_GROUPS:
        latest = pipeline_runs.get_latest_by_pipeline(
            group["pipeline_name"], source=group["source"]
        )
        rows.append(
            {
                "pipeline_name": group["pipeline_name"],
                "source": group["source"],
                "label": group["label"],
                "latest_run": latest,
                "display_status": (
                    pipeline_runs.display_status(latest) if latest else None
                ),
                "summary_obj": (
                    json.loads(latest.summary) if latest and latest.summary else None
                ),
            }
        )
    return render_template("pipelines/admin/index.html", rows=rows)


@bp.route("/admin/pipelines/<pipeline_name>")
@login_required
def history(pipeline_name):
    """Paginated run history for one pipeline (optionally one source)."""
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        abort(400)

    if page < 1 or limit < 1:
        abort(400)

    source = request.args.get("source") or None
    runs, pages, qtt_runs = pipeline_runs.get_paginated(
        pipeline_name, page, limit, source=source
    )

    prev_page = page - 1 if page > 1 else None
    next_page = page + 1 if page < pages else None

    return render_template(
        "pipelines/admin/history.html",
        pipeline_name=pipeline_name,
        source=source,
        label=_group_label(pipeline_name, source),
        runs=runs,
        display_statuses={run.id: pipeline_runs.display_status(run) for run in runs},
        summaries={
            run.id: (json.loads(run.summary) if run.summary else None) for run in runs
        },
        detail_urls={run.id: _detail_url(run) for run in runs},
        curr_page=page,
        prev_page=prev_page,
        next_page=next_page,
        pages=pages,
        limit=limit,
        qtt_runs=qtt_runs,
    )


@bp.route("/admin/pipelines/<pipeline_name>/<int:run_id>")
@login_required
def detail(pipeline_name, run_id):
    """Full item list for one specific run."""
    run = pipeline_runs.get_by_id(run_id)
    if run is None or run.pipeline_name != pipeline_name:
        abort(404)

    screenings, metadata_attempts, poster_attempts, alerts = [], [], [], []
    if pipeline_name == "import-json":
        screenings = get_screenings_by_run(run_id)
    elif pipeline_name == "fetch-movie-metadata":
        metadata_attempts = get_metadata_attempts_by_run(run_id)
    elif pipeline_name == "fetch-posters":
        poster_attempts = get_poster_attempts_by_run(run_id)
    elif pipeline_name == "generate-alerts":
        alerts = get_alerts_by_run(run_id)

    return render_template(
        "pipelines/admin/detail.html",
        run=run,
        label=_group_label(run.pipeline_name, run.source),
        display_status=pipeline_runs.display_status(run),
        screenings=screenings,
        metadata_attempts=metadata_attempts,
        poster_attempts=poster_attempts,
        alerts=alerts,
    )
