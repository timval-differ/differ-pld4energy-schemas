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
import logging
import re
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .archive import SpecError
from .convert import NotALogbook, UnsafeLogbookFile
from .rules import step_time_warnings

STATIC = Path(__file__).parent / 'static'

logger = logging.getLogger(__name__)

# What reading a form of the wrong shape raises, e.g. a list where an object is
# expected. The form comes from the browser or from a draft in an upload.
MALFORMED = (
    TypeError,
    AttributeError,
    KeyError,
    IndexError,
    ValueError,
    ArithmeticError,
)


@contextmanager
def malformed_request(endpoint: str):
    """Answer a form or archive of the wrong shape with a 400, not a 500."""
    try:
        yield
    except SpecError:
        # A bug in the plugin: answered with a 500, and logged in full.
        logger.exception('%s: the form definition does not fit the schema', endpoint)
        raise
    except MALFORMED as error:
        # With the traceback: a bug that raises one of these looks the same.
        logger.warning('%s: malformed request: %r', endpoint, error, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f'Malformed form: {type(error).__name__}: {error}',
        ) from error


def asset_version(name: str) -> str:
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12]


def static_version() -> str:
    """
    A version of all static files together. The page and the server compare it
    to tell when NOMAD has to be restarted after an update, so a change to any
    script (not only app.js) counts.
    """
    digest = hashlib.sha256()
    for path in sorted(STATIC.iterdir()):
        if path.is_file():
            digest.update(path.name.encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()[:12]


def index_page(title: str) -> str:
    """
    The page, linking every static file it names (`static/<name>"`) with a
    version taken from its content. Browsers cache static files, so without it
    an updated dashboard could run an old app.js against a new form definition.
    """
    page = (STATIC / 'index.html').read_text(encoding='utf-8')
    page = re.sub(
        r'static/([\w.-]+)"',
        lambda match: f'static/{match[1]}?v={asset_version(match[1])}"',
        page,
    )
    page = page.replace('{{title}}', html.escape(title))
    return page.replace('{{script_version}}', static_version())


class RevalidatedStaticFiles(StaticFiles):
    """
    Static files the browser asks about again on every use (answered with 304
    while unchanged). Scripts loaded by other scripts get no `?v=`, so they must
    not be cached by guesswork either.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers['Cache-Control'] = 'no-cache'
        return response


class FormRequest(BaseModel):
    form: dict
    logbook_file: str | None = Field(None, max_length=255)
    # The files a save overwrites, as they are in the upload (convert.form_to_files).
    existing: dict | None = None


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
    spec = {**form_spec, 'script_version': static_version()}

    @app.get('/', include_in_schema=False)
    async def index():
        # Never cached, so a new version always loads its matching assets.
        return HTMLResponse(index_page(title), headers={'Cache-Control': 'no-cache'})

    app.mount('/static', RevalidatedStaticFiles(directory=STATIC), name='static')

    @app.get('/api/spec')
    async def get_spec():
        return spec

    @app.post('/api/validate')
    async def post_validate(request: FormRequest):
        with malformed_request('validate'):
            return {
                'errors': rules.validate(request.form, spec),
                'warnings': step_time_warnings(request.form),
            }

    @app.post('/api/archive')
    async def post_archive(request: FormRequest):
        with malformed_request('archive'):
            errors = rules.validate(request.form, spec)
            if errors:
                return {'errors': errors, 'files': []}
            try:
                result = converter.form_to_files(
                    request.form, spec, request.logbook_file, request.existing
                )
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
        with malformed_request('draft-name'):
            errors = rules.validate_draft(request.form, spec)
            if errors:
                return {'errors': errors, 'path': None}
            return {'errors': [], 'path': converter.draft_path(request.form)}

    @app.post('/api/form-from-archive')
    async def post_form_from_archive(request: ArchiveRequest):
        with malformed_request('form-from-archive'):
            try:
                if request.mode == 'recipe':
                    return converter.recipe_to_form(request.data, spec)
                return converter.archive_to_form(request.data, spec)
            except NotALogbook as error:
                raise HTTPException(status_code=400, detail=str(error)) from error

    return app
