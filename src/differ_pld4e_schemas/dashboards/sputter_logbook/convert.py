"""
Conversion between the sputter logbook form data and NOMAD archive files, see
`dashboards.common.convert`. Besides the common sections, the form has the
general comments of the run, kept as the logbook's description.
"""

from __future__ import annotations

from differ_pld4e_schemas import sps_deposition

from ..common.archive import fill, read
from ..common.convert import LogbookConverter, sections_of
from .rules import RULES
from .spec import DRAFT_DIR, LOGBOOK_SECTIONS

__all__ = ['archive_to_form', 'draft_path', 'form_to_files', 'recipe_to_form']


class SputterConverter(LogbookConverter):
    def extra_to_archive(
        self, data: dict, spec: dict, logbook: dict, references: dict
    ) -> None:
        system = data['run']['system']
        fill(
            logbook,
            self.logbook_sections[system],
            sections_of(spec)['comments']['fields'],
            data.get('comments') or {},
            data,
        )

    def extra_to_form(
        self, data: dict, spec: dict, form: dict, by_reference: dict
    ) -> None:
        system = form['run']['system']
        form['comments'] = read(
            data, self.logbook_sections[system], sections_of(spec)['comments']['fields']
        )


CONVERTER = SputterConverter(LOGBOOK_SECTIONS, sps_deposition, RULES, DRAFT_DIR)
archive_to_form = CONVERTER.archive_to_form
draft_path = CONVERTER.draft_path
form_to_files = CONVERTER.form_to_files
recipe_to_form = CONVERTER.recipe_to_form
