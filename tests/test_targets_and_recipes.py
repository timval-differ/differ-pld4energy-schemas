"""
Targets that cannot be read, references that name an entry by its file, and
what a recipe copies of the run it comes from.
"""

import json

import pytest
from helpers import ENTRY_CREATE_TIME
from helpers import pld_forms as pld
from helpers import sputter_forms as sputter
from helpers.database import database_uploads
from helpers.nomad_harness import UPLOAD_ID, errors, process_file, warnings
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.utils import generate_entry_id
from structlog.testing import CapturingLogger

from differ_pld4e_schemas.gas import BackgroundGas
from differ_pld4e_schemas.pld_deposition import (
    RecipeLoader,
    SAPLDDepositionStep,
    SAPLDHeatingStep,
    SAPLDLogbook,
    SelectedTarget,
)
from differ_pld4e_schemas.process_steps import RUN_SPECIFIC
from differ_pld4e_schemas.references import copy_section, reference_key
from differ_pld4e_schemas.sps_deposition import SelectedSputterTarget, SPSLogbook
from differ_pld4e_schemas.target import PLDTarget

MISSING = '../uploads/target_db/archive/missing#/data'


def _normalize(logbook):
    logger = CapturingLogger()
    archive = EntryArchive(
        data=logbook, metadata=EntryMetadata(entry_create_time=ENTRY_CREATE_TIME)
    )
    logbook.normalize(archive, logger)
    return [(call[0], call[1][0]) for call in logger.calls]


def _write(directory, name, logbook):
    (directory / name).write_text(
        json.dumps({'data': logbook.m_to_dict(with_root_def=True)}), encoding='utf-8'
    )


# A target that cannot be read


@pytest.mark.parametrize(
    'logbook, selected',
    [
        (SAPLDLogbook, SelectedTarget(target=MISSING, target_number=2, material='STO')),
        (
            SPSLogbook,
            SelectedSputterTarget(target=MISSING, target_number=1, material='Ta'),
        ),
    ],
    ids=['pld', 'sps'],
)
def test_unreadable_target_is_reported_and_keeps_its_copies(
    tmp_path, logbook, selected
):
    _write(
        tmp_path,
        'run.archive.json',
        logbook(datetime=ENTRY_CREATE_TIME, targets=[selected]),
    )
    archive, logs, _ = process_file(
        tmp_path, 'run.archive.json', other_uploads=database_uploads()
    )
    found = [log['event'] for log in errors(logs)]
    # Reported, but the rest of the logbook is still normalized.
    assert not any('could not normalize section' in event for event in found)
    assert any('cannot be read' in event for event in found)
    assert archive.data.targets[0].material == selected.material
    assert archive.data.name  # the run got its default name


def test_cleared_target_clears_what_was_copied_from_it():
    pld_target = SelectedTarget(material='STO', manufacturer='x', target_number=2)
    sps_target = SelectedSputterTarget(material='Ta', diameter=0.0508, target_number=3)
    pld_logbook = SAPLDLogbook(targets=[pld_target])
    sps_logbook = SPSLogbook(targets=[sps_target])
    _normalize(pld_logbook)
    records = _normalize(sps_logbook)
    assert (pld_target.material, pld_target.manufacturer) == (None, None)
    assert (sps_target.material, sps_target.diameter) == (None, None)
    # The diameter check no longer uses a value of the cleared target.
    assert not any('takes' in message for _, message in records)


def test_unreadable_recipe_is_reported():
    logbook = SAPLDLogbook(load_recipe=RecipeLoader(recipe=MISSING, apply_recipe=True))
    records = _normalize(logbook)
    assert not logbook.steps
    assert any('recipe cannot be read' in message for level, message in records)


# References by entry ID or by file


def test_references_by_file_and_by_id_are_the_same():
    entry_id = generate_entry_id('U', 't.archive.yaml')

    class Proxy:
        def __init__(self, url):
            self.m_proxy_value = url

    keys = {
        reference_key(Proxy('../uploads/U/archive/mainfile/t.archive.yaml#data')),
        reference_key(Proxy('../upload/archive/mainfile/t.archive.yaml#/data'), 'U'),
        reference_key(Proxy(f'../uploads/U/archive/{entry_id}#/data')),
        reference_key(Proxy(f'../uploads/U/archive/{entry_id}#data')),
    }
    assert keys == {(entry_id, 'data')}


def test_step_target_by_file_matches_the_selected_target_by_id(tmp_path):
    # A target in the logbook's own upload, named by its ID and by its file.
    # (NOMAD turns a mainfile reference into an ID of the referring entry's
    # own upload, so only same-upload references can name a file.)
    _write(tmp_path, 'sto.archive.json', PLDTarget(name='STO', material='SrTiO3'))
    entry_id = generate_entry_id(UPLOAD_ID, 'sto.archive.json')
    _write(
        tmp_path,
        'run.archive.json',
        SAPLDLogbook(
            datetime=ENTRY_CREATE_TIME,
            targets=[
                SelectedTarget(
                    target=f'../uploads/{UPLOAD_ID}/archive/{entry_id}#/data',
                    target_number=4,
                )
            ],
            steps=[
                SAPLDDepositionStep(
                    target='../upload/archive/mainfile/sto.archive.json#data'
                )
            ],
        ),
    )
    archive, logs, _ = process_file(
        tmp_path, 'run.archive.json', other_uploads=database_uploads()
    )
    assert not any('not selected' in w for w in warnings(logs))
    assert archive.data.steps[0].target_number == 4  # noqa: PLR2004


# What a recipe copies


def _recipe():
    target = PLDTarget(material='Fe2O3')
    return SAPLDLogbook(
        name='Fe2O3 on STO',
        targets=[SelectedTarget(target_number=1, target=target)],
        steps=[
            SAPLDHeatingStep(
                temperature_setpoint=973,
                start_time='2026-10-22T09:20:00+02:00',
                end_time='2026-10-22T10:05:00+02:00',
                comment='Heater flickered.',
                background_gases=[
                    BackgroundGas(gas='O2', flow_setpoint=1e-7, flow_readout=0.9e-7)
                ],
            ),
            SAPLDDepositionStep(target=target),
        ],
    )


def test_recipe_copies_how_to_run_a_step_not_what_happened():
    recipe = _recipe()
    logbook = SAPLDLogbook(load_recipe=RecipeLoader(recipe=recipe, apply_recipe=True))
    _normalize(logbook)
    heating, deposition = logbook.steps
    assert heating.temperature_setpoint is not None
    assert (heating.start_time, heating.end_time, heating.comment) == (None, None, None)
    gas = heating.background_gases[0]
    assert gas.flow_setpoint is not None
    assert gas.flow_readout is None
    # The recipe itself is not changed.
    assert recipe.steps[0].comment == 'Heater flickered.'


def test_copy_section_excludes_at_every_depth():
    step = _recipe().steps[0]
    copied = copy_section(step, frozenset({'flow_readout'}))
    assert copied.background_gases[0].flow_readout is None
    assert copy_section(step).background_gases[0].flow_readout is not None


def test_read_out_quantities_are_run_specific():
    from differ_pld4e_schemas import m_package

    names = {
        quantity.name
        for section in m_package.section_definitions
        for quantity in section.all_quantities.values()
    }
    read_outs = {
        name
        for name in names
        if name.endswith('_readout')
        or name.startswith('actual_')
        or name.endswith('_measured')
    }
    assert read_outs <= RUN_SPECIFIC


def test_dashboard_recipe_drops_the_same_values():
    data = pld.form(steps__0__step_comments='Heater flickered.')
    recipe = pld.recipe_to_form(pld._logbook(data), pld.SPEC)
    for step in recipe['steps']:
        assert not [key for key in step if key.endswith('_flow_readout')]
        assert 'actual_voltage' not in step
        assert 'actual_current' not in step
        assert 'step_comments' not in step
    assert recipe['steps'][0]['gas_O2_flow_setpoint'] == pytest.approx(5)


def test_sputter_logbook_says_it_does_not_record_the_recipe():
    data = {**sputter.FORM, 'recipe': '../uploads/u/archive/r#/data'}
    result = sputter.form_to_files(data, sputter.SPEC)
    assert [w['path'] for w in result['warnings']] == ['recipe']


def test_recipe_does_not_copy_heater_read_outs():
    from differ_pld4e_schemas.pld_deposition import LAPLDDepositionStep, LAPLDLogbook

    recipe = LAPLDLogbook(
        steps=[
            LAPLDDepositionStep(
                supply_voltage=20, actual_voltage=19.8, actual_current=4.9
            )
        ]
    )
    logbook = LAPLDLogbook(load_recipe=RecipeLoader(recipe=recipe, apply_recipe=True))
    _normalize(logbook)
    (step,) = logbook.steps
    assert step.supply_voltage is not None
    assert (step.actual_voltage, step.actual_current) == (None, None)


def test_recipe_keeps_a_planned_duration_but_not_one_from_its_times():
    planned = SAPLDHeatingStep(temperature_setpoint=973, duration=600)
    timed = SAPLDHeatingStep(
        start_time='2026-10-22T09:20:00+02:00',
        end_time='2026-10-22T10:05:00+02:00',
        duration=2700,
    )
    recipe = SAPLDLogbook(steps=[planned, timed])
    logbook = SAPLDLogbook(load_recipe=RecipeLoader(recipe=recipe, apply_recipe=True))
    _normalize(logbook)
    assert logbook.steps[0].duration.to('s').magnitude == pytest.approx(600)
    assert logbook.steps[1].duration is None


def test_file_names_in_references_may_be_encoded():
    class Proxy:
        def __init__(self, url):
            self.m_proxy_value = url

    plain = reference_key(Proxy('../uploads/U/archive/mainfile/a b.archive.json#data'))
    encoded = reference_key(
        Proxy('../uploads/U/archive/mainfile/a%20b.archive.json#data')
    )
    assert plain == encoded
