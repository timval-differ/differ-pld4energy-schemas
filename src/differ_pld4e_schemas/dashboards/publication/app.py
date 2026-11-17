"""
FastAPI app of the publication dashboard.

The page lists the user's uploads (through the NOMAD API, with the user's
session); exporting one runs here, on the server, as that user.

NOMAD's GUI keeps the user's session in a cookie for NOMAD's API only (its
path is `<base>/api`), so the browser does not send it to a dashboard. The
page therefore asks the API for a short-lived signature token
(`/auth/signature_token`) and sends it with each request here, as NOMAD's own
GUI does for downloads; NOMAD's `get_current_user` checks it.

The endpoints are plain functions, not `async`: FastAPI runs them in its
thread pool, so their file and database access does not hold up other requests.
"""

# No `from __future__ import annotations`: FastAPI must see the `User` type of
# the endpoints, which is made in `create_app`.
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from differ_pld4e_schemas.snapshot import build_snapshot

from ..common.app import RevalidatedStaticFiles
from .jobs import AlreadyRunning, Jobs
from .source import NomadFilesSource

STATIC = Path(__file__).parent / 'static'
COMMON_STATIC = Path(__file__).parents[1] / 'common' / 'static'


class ExportRequest(BaseModel):
    upload_id: str = Field(min_length=1, max_length=64, pattern=r'^[\w-]+$')


def current_user():
    """The logged-in user: NOMAD's own check of the token."""
    from nomad.app.v1.routers.auth import get_current_user
    from nomad.auth.scopes import Scope

    return get_current_user([Scope.UPLOADS_READ], allow_anonymous=False)


def default_jobs() -> Jobs:
    from nomad.config import config

    return Jobs(Path(config.fs.tmp) / 'publication-exports')


def api_url() -> str:
    from nomad.config import config

    return config.api_url(api='api/v1')


def create_app(jobs: Jobs | None = None, user_dependency=None) -> FastAPI:
    jobs = jobs or default_jobs()
    User = Annotated[object, Depends(user_dependency or current_user())]
    app = FastAPI(title='Publication export dashboard')

    @app.get('/', include_in_schema=False)
    def index():
        page = (STATIC / 'index.html').read_text(encoding='utf-8')
        return HTMLResponse(page, headers={'Cache-Control': 'no-cache'})

    # Served at the same relative paths as on disk (dashboards/<name>/static/),
    # so the page's imports of the logbook dashboards' style and NOMAD API
    # helpers work in the browser and in the type check alike.
    app.mount(
        '/publication/static',
        RevalidatedStaticFiles(directory=STATIC),
        name='static',
    )
    app.mount(
        '/common/static',
        RevalidatedStaticFiles(directory=COMMON_STATIC),
        name='common',
    )

    @app.post('/api/exports', status_code=202)
    def start_export(request: ExportRequest, user: User):
        from nomad.app.v1.routers.uploads.utils import get_upload_with_read_access

        # Answer at once (404, 403) if the upload cannot be exported at all.
        upload = get_upload_with_read_access(
            request.upload_id, user, include_others=True
        )
        if upload.process_running:
            raise HTTPException(
                409, 'The upload is being processed. Export it when it is done.'
            )
        source = NomadFilesSource(user)
        url = api_url()
        try:
            return jobs.start(
                user.user_id,
                request.upload_id,
                lambda: build_snapshot(request.upload_id, source, url),
            )
        except AlreadyRunning:
            raise HTTPException(
                409, 'Your previous export is still running. Wait for it first.'
            ) from None

    @app.get('/api/exports/{job_id}')
    def get_export(job_id: str, user: User):
        try:
            return jobs.get(job_id, user.user_id)
        except KeyError:
            raise HTTPException(404, 'No such export.') from None

    @app.get('/api/exports/{job_id}/download')
    def download_export(job_id: str, user: User):
        try:
            path = jobs.zip_path(job_id, user.user_id)
        except KeyError:
            raise HTTPException(404, 'No such export, or it is not ready.') from None
        return FileResponse(path, media_type='application/zip', filename=path.name)

    return app
