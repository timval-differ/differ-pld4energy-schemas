"""
The form rules exist twice: in Python (common/rules.py, what the server checks
before it saves) and in the browser (static/rules.js, for feedback while
typing). This test runs many forms of both dashboards through the Python rules
and keeps the results in tests/js/fixtures/parity.json; tests/js/parity.test.js
runs the same forms through rules.js and must get the same results.

After a deliberate change to the rules, regenerate the file with

    UPDATE_JS_PARITY=1 uv run pytest tests/dashboards/test_js_parity.py

and run `npm test`: it fails until rules.js agrees.
"""

import copy
import json
import os
from pathlib import Path

import test_pld_logbook as pld
import test_sputter_logbook as sputter

from differ_pld4e_schemas.dashboards.common.rules import step_time_warnings
from differ_pld4e_schemas.dashboards.pld_logbook import rules as pld_rules
from differ_pld4e_schemas.dashboards.pld_logbook.spec import form_spec as pld_spec
from differ_pld4e_schemas.dashboards.sputter_logbook import rules as sputter_rules
from differ_pld4e_schemas.dashboards.sputter_logbook.spec import (
    form_spec as sputter_spec,
)

FIXTURE = Path(__file__).resolve().parents[1] / 'js' / 'fixtures' / 'parity.json'
DELETE = object()

# Changes to a dashboard's complete form; each makes one case. Paths that do
# not exist in a dashboard's form are skipped for it.
CHANGES = {
    'complete': {},
    # Dates and times
    'date not in the calendar': {'run.date': '2026-02-30'},
    'date of a leap year': {'run.date': '2024-02-29'},
    'date without dashes': {'run.date': '20261022'},
    'date as a week': {'run.date': '2026-W43-4'},
    'date with a time': {'run.date': '2026-10-22T09:15'},
    'time past midnight': {'run.time': '25:99'},
    'time with one digit': {'run.time': '9:30'},
    'time with seconds': {'run.time': '09:30:00'},
    'no date': {'run.date': DELETE},
    'no time': {'run.time': ''},
    'unknown system': {'run.system': 'XX'},
    # Numbers
    'number too large': {'chamber.base_pressure': '1e400'},
    'number with a decimal comma': {'chamber.base_pressure': '1,5e-8'},
    'number with two commas': {'chamber.base_pressure': '1,000,5'},
    'number with an underscore': {'chamber.base_pressure': '1_000'},
    'number with spaces around': {'chamber.base_pressure': ' 2.5 '},
    'number with a space inside': {'chamber.base_pressure': '1 000'},
    'number in other digits': {'chamber.base_pressure': '١٢'},
    'number as a word': {'chamber.base_pressure': 'abc'},
    'number infinity': {'chamber.base_pressure': 'Infinity'},
    'number as JSON number': {'chamber.base_pressure': 0.002},
    'negative number below the minimum': {'chamber.base_pressure': -5},
    'whole number with a fraction': {
        'steps.1.film_thickness_pulses': '10.5',
        'steps.1.film_thickness_unit': 'pulses',
    },
    # Samples
    'no samples': {'samples': []},
    'external sample with films': {
        'samples.0.origin': 'External sample',
        'samples.0.substrate': DELETE,
        'samples.0.substrate_details': 'MgO (001)',
        'samples.0.prior_films': [
            {'material': 'SrRuO3', 'thickness': '12'},
            {'material': 'Pt'},
            {'thickness': '3'},
        ],
    },
    'existing sample': {
        'samples.0.origin': 'Existing sample',
        'samples.0.sample': '../uploads/u0/archive/s0#/data',
    },
    'saved sample keeps its ID': {
        'samples.0.ref': '../upload/archive/mainfile/x.archive.json#data',
        'samples.0.sample_id': 'LA-PLD_2026-01-01_08:00_S03',
    },
    # Targets
    'target without material': {'targets.0.material': DELETE},
    'target not chosen': {'targets.0.target': DELETE},
    'target outside the database': {
        'targets.0.target': '../uploads/elsewhere/archive/t#/data'
    },
    # Steps
    'no steps': {'steps': []},
    'unknown step type': {'steps.0.type': 'no-such-step'},
    'step across midnight': {
        'steps.0.start_time': '23:30',
        'steps.0.end_time': '00:10',
    },
    'step ends before it starts': {'steps.0.end_time': '09:00'},
    'steps overlap': {'steps.1.start_time': '09:30'},
    'film in pulses': {
        'steps.1.film_thickness_unit': 'pulses',
        'steps.1.film_thickness_pulses': '1500',
    },
    'thick film': {'steps.1.film_thickness': 1234567},
    'thin film': {'steps.1.film_thickness': 0.00005},
    'film of 12.5 nm': {'steps.1.film_thickness': '12,5'},
    'step on an unknown sample': {'steps.1.sample': 'new:nobody'},
    'step with an unknown target': {'steps.1.target': 'missing'},
}


def _change(form, path, value):
    *parents, key = path.split('.')
    target = form
    for parent in parents:
        target = target[int(parent)] if parent.isdigit() else target[parent]
    if not isinstance(target, dict):
        raise KeyError(path)
    if value is DELETE:
        target.pop(key, None)
    else:
        target[key] = value


def _forms(base: dict, extra: dict) -> dict:
    forms = {'empty form': {}, **extra}
    for name, changes in CHANGES.items():
        form = copy.deepcopy(base)
        try:
            for path, value in changes.items():
                _change(form, path, value)
        except (IndexError, KeyError, TypeError):
            continue
        forms[name] = form
    return forms


def _computed_values(rules, spec: dict, form: dict) -> dict:
    """Every computed field of the form, by its path."""
    values = {}
    for section in spec['sections']:
        key = section['key']
        if section['kind'] == 'object':
            items = [(key, section['fields'], form.get(key) or {})]
        else:
            items = []
            for index, item in enumerate(form.get(key) or []):
                fields = section.get('fields') or []
                if section['kind'] == 'variant_list':
                    fields = (section['variants'].get(item.get('type')) or {}).get(
                        'fields', []
                    )
                items.append((f'{key}.{index}', fields, item))
        for path, fields, local in items:
            for field in fields:
                if field['kind'] == 'computed':
                    values[f'{path}.{field["key"]}'] = rules.compute(
                        field['compute'], local, form
                    )
    return values


def _dashboard(rules, spec: dict, forms: dict) -> dict:
    spec = json.loads(json.dumps(spec))  # as the browser gets it
    cases = []
    for name, form in forms.items():
        cases.append(
            {
                'name': name,
                'form': form,
                'errors': rules.validate(form, spec),
                'warnings': step_time_warnings(form),
                'draft_errors': rules.validate_draft(form, spec),
                'computed': _computed_values(rules, spec, form),
            }
        )
    return {'spec': spec, 'cases': cases}


def parity_cases() -> dict:
    return {
        'pld': _dashboard(
            pld_rules.RULES,
            pld_spec(),
            _forms(
                pld.FORM,
                {
                    'complete SA-PLD form': pld.sa_form(),
                    'annealing only': pld.annealing_form(),
                },
            ),
        ),
        'sputter': _dashboard(
            sputter_rules.RULES, sputter_spec(), _forms(sputter.FORM, {})
        ),
    }


def _text(cases: dict) -> str:
    return json.dumps(cases, indent=1, sort_keys=True, ensure_ascii=False) + '\n'


def test_parity_cases_are_up_to_date():
    expected = _text(parity_cases())
    if os.environ.get('UPDATE_JS_PARITY'):
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(expected, encoding='utf-8', newline='\n')
    current = FIXTURE.read_text(encoding='utf-8') if FIXTURE.exists() else ''
    assert current == expected, (
        'The Python rules or forms changed: regenerate tests/js/fixtures/parity.json '
        'with UPDATE_JS_PARITY=1 and check that `npm test` still passes.'
    )


def test_parity_cases_cover_errors_and_computed_values():
    for name, dashboard in parity_cases().items():
        cases = {case['name']: case for case in dashboard['cases']}
        assert cases['complete']['errors'] == [], name
        assert sum(bool(case['errors']) for case in cases.values()) > 10, name  # noqa: PLR2004
        assert any(case['warnings'] for case in cases.values()), name
        assert any(
            value for case in cases.values() for value in case['computed'].values()
        ), name
