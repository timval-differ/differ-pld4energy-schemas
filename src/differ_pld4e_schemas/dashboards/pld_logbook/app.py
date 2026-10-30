"""
FastAPI app of the PLD logbook dashboard.

The browser page (`static/`) talks to the NOMAD API directly for everything
that needs the user's session (uploads, searching targets, writing files). This
app only serves the page and the form logic that must be the same everywhere:
the form definition, validation and the conversion to archive files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .convert import archive_to_form, draft_path, form_to_files, recipe_to_form
from .rules import validate, validate_draft
from .spec import form_spec

STATIC = Path(__file__).parent / 'static'
ASSETS = ('app.js', 'pdf.js', 'style.css')


def asset_version(name: str) -> str:
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12]


def index_page() -> str:
    """
    The page, linking its script and style sheet with a version taken from their
    content. Browsers cache static files, so without it an updated dashboard
    could run an old app.js against a new form definition.
    """
    page = (STATIC / 'index.html').read_text(encoding='utf-8')
    for name in ASSETS:
        page = page.replace(
            f'static/{name}"', f'static/{name}?v={asset_version(name)}"'
        )
    return page.replace('{{script_version}}', asset_version('app.js'))


class FormRequest(BaseModel):
    form: dict
    logbook_file: str | None = None


class ArchiveRequest(BaseModel):
    data: dict
    mode: str = 'edit'


def create_app() -> FastAPI:
    app = FastAPI(title='PLD logbook dashboard')
    # The static files are read from disk on every request, but the Python code
    # only on start. The page compares this version with its own to tell when
    # NOMAD has to be restarted after an update.
    spec = {**form_spec(), 'script_version': asset_version('app.js')}

    @app.get('/', include_in_schema=False)
    async def index():
        # Never cached, so a new version always loads its matching assets.
        return HTMLResponse(index_page(), headers={'Cache-Control': 'no-cache'})

    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    @app.get('/api/spec')
    async def get_spec():
        return spec

    @app.post('/api/validate')
    async def post_validate(request: FormRequest):
        return {'errors': validate(request.form, spec)}

    @app.post('/api/archive')
    async def post_archive(request: FormRequest):
        errors = validate(request.form, spec)
        if errors:
            return {'errors': errors, 'files': []}
        result = form_to_files(request.form, spec, request.logbook_file)
        return {'errors': [], **result}

    @app.post('/api/draft-name')
    async def post_draft_name(request: FormRequest):
        """
        Where a draft of the form is kept in the upload. Drafts are plain files,
        not entries: only a complete logbook becomes an entry.
        """
        errors = validate_draft(request.form, spec)
        if errors:
            return {'errors': errors, 'path': None}
        return {'errors': [], 'path': draft_path(request.form)}

    @app.post('/api/form-from-archive')
    async def post_form_from_archive(request: ArchiveRequest):
        try:
            if request.mode == 'recipe':
                return recipe_to_form(request.data, spec)
            return archive_to_form(request.data, spec)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return app
