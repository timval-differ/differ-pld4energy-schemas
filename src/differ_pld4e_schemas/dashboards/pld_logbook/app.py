"""
FastAPI app of the PLD logbook dashboard.

The browser page (`static/`) talks to the NOMAD API directly for everything
that needs the user's session (uploads, searching targets, writing files). This
app only serves the page and the form logic that must be the same everywhere:
the form definition, validation and the conversion to archive files.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .convert import archive_to_form, draft_path, form_to_files, recipe_to_form
from .rules import validate, validate_draft
from .spec import form_spec

STATIC = Path(__file__).parent / 'static'


class FormRequest(BaseModel):
    form: dict
    logbook_file: str | None = None


class ArchiveRequest(BaseModel):
    data: dict
    mode: str = 'edit'


def create_app() -> FastAPI:
    app = FastAPI(title='PLD logbook dashboard')
    spec = form_spec()

    @app.get('/', include_in_schema=False)
    async def index():
        return FileResponse(STATIC / 'index.html')

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
