"""
FastAPI app of a logbook dashboard.

The browser page (`static/`) talks to the NOMAD API directly for everything
that needs the user's session (uploads, searching targets, writing files). This
app only serves the page and the form logic that must be the same everywhere:
the form definition, validation and the conversion to archive files. Every
logbook dashboard serves the same page; what differs comes with its form
definition (`client` holds the page's texts and settings).
"""

from __future__ import annotations

import hashlib
import html
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .convert import UnsafeLogbookFile
from .rules import step_time_warnings

STATIC = Path(__file__).parent / 'static'
ASSETS = ('app.js', 'pdf.js', 'style.css')


def asset_version(name: str) -> str:
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12]


def index_page(title: str) -> str:
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
    page = page.replace('{{title}}', html.escape(title))
    return page.replace('{{script_version}}', asset_version('app.js'))


class FormRequest(BaseModel):
    form: dict
    logbook_file: str | None = Field(None, max_length=255)


class ArchiveRequest(BaseModel):
    data: dict
    mode: str = 'edit'


def create_app(form_spec: dict, rules, converter) -> FastAPI:
    """
    `rules` is the dashboard's `LogbookRules`, `converter` its
    `LogbookConverter`.
    """
    title = form_spec['client']['title']
    app = FastAPI(title=f'{title} dashboard')
    # The static files are read from disk on every request, but the Python code
    # only on start. The page compares this version with its own to tell when
    # NOMAD has to be restarted after an update.
    spec = {**form_spec, 'script_version': asset_version('app.js')}

    @app.get('/', include_in_schema=False)
    async def index():
        # Never cached, so a new version always loads its matching assets.
        return HTMLResponse(index_page(title), headers={'Cache-Control': 'no-cache'})

    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    @app.get('/api/spec')
    async def get_spec():
        return spec

    @app.post('/api/validate')
    async def post_validate(request: FormRequest):
        return {
            'errors': rules.validate(request.form, spec),
            'warnings': step_time_warnings(request.form),
        }

    @app.post('/api/archive')
    async def post_archive(request: FormRequest):
        errors = rules.validate(request.form, spec)
        if errors:
            return {'errors': errors, 'files': []}
        try:
            result = converter.form_to_files(request.form, spec, request.logbook_file)
        except UnsafeLogbookFile as error:
            return {
                'errors': [{'path': 'logbook_file', 'message': str(error)}],
                'files': [],
            }
        return {'errors': [], **result}

    @app.post('/api/draft-name')
    async def post_draft_name(request: FormRequest):
        """
        Where a draft of the form is kept in the upload. Drafts are plain files,
        not entries: only a complete logbook becomes an entry.
        """
        errors = rules.validate_draft(request.form, spec)
        if errors:
            return {'errors': errors, 'path': None}
        return {'errors': [], 'path': converter.draft_path(request.form)}

    @app.post('/api/form-from-archive')
    async def post_form_from_archive(request: ArchiveRequest):
        try:
            if request.mode == 'recipe':
                return converter.recipe_to_form(request.data, spec)
            return converter.archive_to_form(request.data, spec)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return app
