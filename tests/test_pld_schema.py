import os.path

import numpy as np
import pytest
import yaml
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.data import EntryData
from structlog.testing import CapturingLogger

import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.gas import BackgroundGas
from differ_pld4e_schemas.in_situ import LAEDS, InSituTechniques, energy_axis
from differ_pld4e_schemas.laser import LaserCalibration, LaserParameters
from differ_pld4e_schemas.pld_deposition import (
    LAPLDCoolDownStep,
    LAPLDDepositionStep,
    LAPLDHeatingStep,
    LAPLDLogbook,
    LAPLDPreAblationStep,
    LAPLDStep,
    RecipeLoader,
    SAPLDCoolDownStep,
    SAPLDDepositionStep,
    SAPLDHeatingStep,
    SAPLDLogbook,
    SAPLDPreAblationStep,
    SAPLDStep,
    SelectedTarget,
)
from differ_pld4e_schemas.pld_substrate import NewSubstrate, PLDSubstrate
from differ_pld4e_schemas.sputter_deposition import SputterDepositionStep
from differ_pld4e_schemas.target import PLDTarget

TARGET_NUMBER = 3
UUID_LENGTH = 36
NUMBER_OF_CHANNELS = 3

ALL_PLD_STEPS = (
    SAPLDPreAblationStep,
    SAPLDHeatingStep,
    SAPLDDepositionStep,
    SAPLDCoolDownStep,
    LAPLDPreAblationStep,
    LAPLDHeatingStep,
    LAPLDDepositionStep,
    LAPLDCoolDownStep,
)


def _normalize(data):
    archive = EntryArchive(data=data, metadata=EntryMetadata())
    logger = CapturingLogger()
    data.normalize(archive, logger)
    return archive, [(call[0], call[1][0]) for call in logger.calls]


def _calibration(**kwargs):
    calibration = LaserCalibration(**kwargs)
    _normalize_section(calibration)
    return calibration


def _normalize_section(section):
    logger = CapturingLogger()
    section.normalize(EntryArchive(metadata=EntryMetadata()), logger)
    return [(call[0], call[1][0]) for call in logger.calls]


# A1: laser details


def test_transmission_window_2_defaults_to_92():
    assert LaserCalibration().transmission_window_2 == pytest.approx(92)


def test_transmission_window_1_is_calculated():
    calibration = _calibration(energy_before_chamber=0.5, energy_after_chamber=0.4)
    assert calibration.transmission_window_1 == pytest.approx(0.8 / 0.92 * 100)


def test_transmission_window_1_is_recalculated_without_manual_flag():
    calibration = _calibration(
        energy_before_chamber=0.5, energy_after_chamber=0.4, transmission_window_1=50
    )
    assert calibration.transmission_window_1 == pytest.approx(0.8 / 0.92 * 100)


def test_transmission_window_1_manual_override_is_kept():
    calibration = _calibration(
        energy_before_chamber=0.5,
        energy_after_chamber=0.4,
        transmission_window_1=90,
        transmission_window_1_manual=True,
    )
    assert calibration.transmission_window_1 == pytest.approx(90)


def test_transmission_window_1_manual_flag_without_value_calculates():
    calibration = _calibration(
        energy_before_chamber=0.5,
        energy_after_chamber=0.4,
        transmission_window_1_manual=True,
    )
    assert calibration.transmission_window_1 == pytest.approx(0.8 / 0.92 * 100)


def test_transmission_window_1_handles_missing_and_zero_inputs():
    assert _calibration(energy_after_chamber=0.4).transmission_window_1 is None
    calibration = LaserCalibration(energy_before_chamber=0, energy_after_chamber=0.4)
    records = _normalize_section(calibration)
    assert calibration.transmission_window_1 is None
    assert any(level == 'warning' for level, _ in records)


# A2: targets


def test_target_entry_is_named_after_material_without_number():
    target = PLDTarget(material='Fe2O3', manufacturer='Praxair')
    archive, _ = _normalize(target)
    assert target.name == 'Fe2O3'
    assert archive.metadata.entry_name == 'Fe2O3'


def test_selected_target_has_user_number_and_database_info():
    target = PLDTarget(name='SrTiO3', material='SrTiO3', manufacturer='Pi-Kem')
    logbook = SAPLDLogbook(
        targets=[SelectedTarget(target_number=TARGET_NUMBER, target=target)]
    )
    _normalize(logbook)
    assert logbook.targets[0].target_number == TARGET_NUMBER
    assert logbook.targets[0].material == 'SrTiO3'
    assert logbook.targets[0].manufacturer == 'Pi-Kem'


def test_duplicate_target_is_reported():
    target = PLDTarget(name='Fe2O3', material='Fe2O3')
    logbook = SAPLDLogbook(
        targets=[
            SelectedTarget(target_number=1, target=target),
            SelectedTarget(target_number=2, target=target),
        ]
    )
    _, records = _normalize(logbook)
    assert any(level == 'error' and 'more than once' in m for level, m in records)


# A4: gas block, step target and spot size


@pytest.mark.parametrize('step', ALL_PLD_STEPS)
def test_every_step_has_gas_block(step):
    assert 'background_gases' in step.m_def.all_sub_sections


def test_gas_block_has_valve_and_flow_readout():
    quantities = BackgroundGas.m_def.all_quantities
    for name in (
        'gas',
        'flow_setpoint',
        'flow_readout',
        'valve_position',
        'valve_position_fixed',
    ):
        assert name in quantities


def test_spot_size_follows_mask_size():
    names = [q.name for q in LaserParameters.m_def.quantities]
    assert names.index('spot_size') == names.index('mask_size') + 1


@pytest.mark.parametrize(
    'step',
    (
        SAPLDPreAblationStep,
        SAPLDDepositionStep,
        LAPLDPreAblationStep,
        LAPLDDepositionStep,
    ),
)
def test_pre_ablation_and_deposition_have_spot_size(step):
    assert step.m_def.all_sub_sections['laser'].sub_section is LaserParameters.m_def


def test_step_target_shows_selected_target():
    fe2o3 = PLDTarget(name='Fe2O3', material='Fe2O3')
    logbook = SAPLDLogbook(
        targets=[SelectedTarget(target_number=TARGET_NUMBER, target=fe2o3)],
        steps=[SAPLDPreAblationStep(), SAPLDDepositionStep()],
    )
    _normalize(logbook)
    for step in logbook.steps:
        assert step.target is fe2o3
        assert step.target_number == TARGET_NUMBER


def test_step_target_not_selected_is_reported():
    logbook = SAPLDLogbook(
        targets=[SelectedTarget(target_number=1, target=PLDTarget(material='Fe2O3'))],
        steps=[SAPLDPreAblationStep(target=PLDTarget(material='8YSZ'))],
    )
    _, records = _normalize(logbook)
    assert logbook.steps[0].target_number is None
    assert any('not selected' in message for _, message in records)


# A5: no sputter step for PLD


@pytest.mark.parametrize('logbook', (SAPLDLogbook, LAPLDLogbook))
def test_sputter_step_is_not_offered_for_pld(logbook):
    steps = logbook.m_def.all_sub_sections['steps'].sub_section
    offered = {steps, *steps.all_inheriting_sections}
    assert SputterDepositionStep.m_def not in offered
    assert not any('Sputter' in section.name for section in offered)


def test_sa_and_la_steps_are_offered_separately():
    sa_steps = set(SAPLDStep.m_def.all_inheriting_sections)
    la_steps = set(LAPLDStep.m_def.all_inheriting_sections)
    assert sa_steps == {step.m_def for step in ALL_PLD_STEPS[:4]}
    assert la_steps == {step.m_def for step in ALL_PLD_STEPS[4:]}


# A3: load recipe


def test_recipe_is_copied_onto_chosen_substrate():
    target = PLDTarget(material='Fe2O3')
    old_substrate = PLDSubstrate(name='old')
    new_substrate = PLDSubstrate(name='new')
    recipe = SAPLDLogbook(
        name='Fe2O3 on STO',
        targets=[SelectedTarget(target_number=1, target=target)],
        steps=[
            SAPLDHeatingStep(temperature_setpoint=973),
            SAPLDDepositionStep(substrate=old_substrate, target=target),
        ],
    )
    logbook = SAPLDLogbook(
        load_recipe=RecipeLoader(
            recipe=recipe, substrate=new_substrate, apply_recipe=True
        )
    )
    _normalize(logbook)

    assert [type(step) for step in logbook.steps] == [
        SAPLDHeatingStep,
        SAPLDDepositionStep,
    ]
    assert logbook.steps[1].substrate is new_substrate
    assert recipe.steps[1].substrate is old_substrate
    assert logbook.steps[1].target_number == 1
    assert logbook.load_recipe.apply_recipe is False
    assert logbook.load_recipe.applied_recipe == 'Fe2O3 on STO'


def test_recipe_from_other_system_is_rejected():
    logbook = LAPLDLogbook(
        load_recipe=RecipeLoader(
            recipe=SAPLDLogbook(steps=[SAPLDHeatingStep()]), apply_recipe=True
        )
    )
    _, records = _normalize(logbook)
    assert not logbook.steps
    assert any(level == 'error' for level, _ in records)


# Substrates


def test_new_substrate_gets_user_id_and_uuid():
    logbook = LAPLDLogbook(
        datetime='2026-10-22T09:00:00+00:00',
        substrates=[NewSubstrate(run_number='12', sample_number='3')],
    )
    _normalize(logbook)
    substrate = logbook.substrates[0]
    assert substrate.sample_user_id == 'LA-PLD_2026-10-22_12_3'
    assert len(substrate.sample_uuid) == UUID_LENGTH


# C2 and C3: LA-PLD


def test_la_heater_scan_defaults_to_polar():
    step = LAPLDDepositionStep()
    _normalize_section(step)
    assert step.heater_scan_type == 'Polar scan'
    assert step.polar_scan is not None
    assert step.cartesian_scan is None
    for name in (
        'radius_start',
        'radius_stop',
        'pulse_spacing',
        'max_laser_frequency',
        'number_of_scans',
    ):
        assert name in step.polar_scan.m_def.all_quantities


def test_la_cartesian_scan():
    step = LAPLDDepositionStep(heater_scan_type='Cartesian scan')
    _normalize_section(step)
    assert step.cartesian_scan is not None
    assert step.polar_scan is None


def test_la_has_extra_carriers_and_particle_reduction_plate():
    la = LAPLDLogbook(
        substrate_carrier='Sample select carrier', particle_reduction_plate='in use'
    )
    assert la.particle_reduction_plate == 'in use'
    with pytest.raises(Exception):
        SAPLDLogbook(substrate_carrier='4" wafer carrier')


# B1: heater stage position


@pytest.mark.parametrize('step', (SAPLDDepositionStep, LAPLDDepositionStep))
def test_heater_stage_position_subsection(step):
    position = step.m_def.all_sub_sections['heater_stage_position'].sub_section
    assert set(position.all_quantities) == {'x', 'y', 'z', 'tilt', 'spin'}


# A6 and section 5: in-situ techniques


def test_in_situ_techniques_are_top_level():
    assert 'in_situ_techniques' in SAPLDLogbook.m_def.all_sub_sections
    assert 'in_situ_techniques' not in SAPLDDepositionStep.m_def.all_sub_sections
    for name in ('rheed', 'mic', 'se', 'la_eds', 'oes', 'shg'):
        assert name in InSituTechniques.m_def.all_sub_sections


def test_la_eds_energy_axis():
    assert np.allclose(energy_axis(3, 100, 10), [100, 110, 120])
    spectrum = LAEDS(
        intensity=[1.0, 5.0, 2.0], energy_offset=100, energy_per_channel=10
    )
    _normalize_section(spectrum)
    assert spectrum.number_of_channels == NUMBER_OF_CHANNELS
    assert np.allclose(spectrum.energy.to('eV').magnitude, [100, 110, 120])
    assert spectrum.figures


# Example entries


@pytest.mark.parametrize(
    'file_name, system',
    (
        ('example_sa_pld.archive.yaml', 'SA-PLD'),
        ('example_la_pld.archive.yaml', 'LA-PLD'),
    ),
)
def test_example_logbooks(file_name, system):
    with open(os.path.join('tests', 'data', file_name)) as archive_file:
        archive = EntryArchive.m_from_dict(yaml.safe_load(archive_file))
    archive.metadata = EntryMetadata()
    logbook = archive.data
    # Like NOMAD processing: normalize sub-sections before their parents.
    for section in reversed(list(logbook.m_all_contents(include_self=True))):
        section.normalize(archive, CapturingLogger())
    assert logbook.pvd_system == system
    assert logbook.laser_details.transmission_window_1 == pytest.approx(
        0.42 / 0.5 / 0.92 * 100
    )
    deposition = next(s for s in logbook.steps if 'Deposition' in s.m_def.name)
    assert deposition.laser.spot_size is not None
    assert deposition.background_gases[0].valve_position_fixed is True


# GUI-created entries store m_def as '<package name>.<section name>'


def test_section_qualified_names_resolve():
    from differ_pld4e_schemas import m_package

    for section in m_package.section_definitions:
        if not issubclass(section.section_cls, EntryData):
            continue
        data = {'data': {'m_def': section.qualified_name()}}
        assert isinstance(EntryArchive.m_from_dict(data).data, section.section_cls)


def test_logbook_qualified_name():
    assert LAPLDLogbook.m_def.qualified_name() == (
        'differ_pld4e_schemas.schema_packages.schema_package.LAPLDLogbook'
    )


def test_copied_same_upload_reference_becomes_absolute():
    from differ_pld4e_schemas.pld_deposition import _absolute_reference

    target = PLDTarget(material='Fe2O3')
    EntryArchive(
        data=target, metadata=EntryMetadata(upload_id='recipe_upload', entry_id='t1')
    )

    class SameUploadProxy:
        m_proxy_value = '../upload/archive/t1#data'

        def m_proxy_resolve(self):
            return target

    assert _absolute_reference(SameUploadProxy()) == (
        '../uploads/recipe_upload/archive/t1#/data'
    )
    assert _absolute_reference(target) == '../uploads/recipe_upload/archive/t1#/data'
    unsaved = PLDTarget(material='8YSZ')
    assert _absolute_reference(unsaved) is unsaved


def test_incomplete_substrates_are_not_reported_as_duplicates():
    logbook = SAPLDLogbook(substrates=[NewSubstrate(), NewSubstrate()])
    _, records = _normalize(logbook)
    assert not any('defined twice' in message for _, message in records)
