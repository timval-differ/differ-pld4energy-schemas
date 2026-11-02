"""FastAPI app of the PLD logbook dashboard, see `dashboards.common.app`."""

from __future__ import annotations

from fastapi import FastAPI

from ..common.app import create_app as create_logbook_app
from .convert import CONVERTER
from .rules import RULES
from .spec import form_spec


def create_app() -> FastAPI:
    return create_logbook_app(form_spec(), RULES, CONVERTER)
