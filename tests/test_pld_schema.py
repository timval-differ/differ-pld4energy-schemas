import os.path

import numpy as np
import pytest
import yaml
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.data import EntryData
from structlog.testing import CapturingLogger

import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.gas import BackgroundGas
from differ_pld4e_schemas.in_situ import (
    LAEDS,
    RHEED,
    InSituTechniques,
    energy_axis,
)
from differ_pld4e_schemas.laser import LaserCalibration, LaserParameters
from differ_pld4e_schemas.pld_deposition import (
    LAPLDAnnealingStep,
    LAPLDCoolDownStep,
    LAPLDDepositionStep,
    LAPLDHeatingStep,
    LAPLDLogbook,
    LAPLDPreAblationStep,
    LAPLDStep,
    RecipeLoader,
    SAPLDAnnealingStep,
    SAPLDCoolDownStep,
    SAPLDDepositionStep,
    SAPLDHeatingStep,
    SAPLDLogbook,
    SAPLDPreAblationStep,
    SAPLDStep,
    SelectedTarget,
)
from differ_pld4e_schemas.sample import Layer, Sample, SampleInRun, sample_name
from differ_pld4e_schemas.sputter_deposition import SputterDepositionStep
from differ_pld4e_schemas.target import PLDTarget

TARGET_NUMBER = 3
UUID_LENGTH = 36
NUMBER_OF_CHANNELS = 3

SA_STEPS = (
    SAPLDPreAblationStep,
    SAPLDHeatingStep,
    SAPLDAnnealingStep,
    SAPLDDepositionStep,
    SAPLDCoolDownStep,
)
LA_STEPS = (
    LAPLDPreAblationStep,
    LAPLDHeatingStep,
    LAPLDAnnealingStep,
    LAPLDDepositionStep,
    LAPLDCoolDownStep,
)
ALL_PLD_STEPS = SA_STEPS + LA_STEPS


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


def test_gas_block_has_flows_and_one_valve_per_step():
    assert set(BackgroundGas.m_def.all_quantities) == {
        'gas',
        'flow_setpoint',
        'flow_readout',
    }
    for step in ALL_PLD_STEPS:
        quantities = step.m_def.all_quantities
        for name in ('atmosphere', 'valve_position', 'valve_position_fixed'):
            assert name in quantities, (step, name)


def test_uhv_with_gases_is_reported():
    step = SAPLDHeatingStep(
        atmosphere='UHV', background_gases=[BackgroundGas(gas='O2')]
    )
    assert any('UHV' in message for _, message in _normalize_section(step))
    assert not _normalize_section(SAPLDHeatingStep(atmosphere='UHV'))


@pytest.mark.parametrize('step', (SAPLDHeatingStep, SAPLDAnnealingStep))
def test_heater_output_is_recorded(step):
    assert 'heater_output' in step.m_def.all_quantities


def test_target_stage_has_z_scan_widths_and_speeds():
    stage = SAPLDPreAblationStep.m_def.all_sub_sections['target_stage'].sub_section
    quantities = set(stage.all_quantities)
    assert 'scan_area' not in quantities
    assert {
        'start_z_position',
        'scan_width_x',
        'scan_width_y',
        'scan_speed_x',
        'scan_speed_y',
    } <= quantities


def test_mask_size_5x18():
    assert '5x18' in LaserParameters.m_def.all_quantities['mask_size'].type._list


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
    assert sa_steps == {step.m_def for step in SA_STEPS}
    assert la_steps == {step.m_def for step in LA_STEPS}


# A3: load recipe


def test_recipe_is_copied_onto_chosen_sample():
    target = PLDTarget(material='Fe2O3')
    old_sample = Sample(sample_id='old')
    new_sample = Sample(sample_id='new')
    recipe = SAPLDLogbook(
        name='Fe2O3 on STO',
        targets=[SelectedTarget(target_number=1, target=target)],
        steps=[
            SAPLDHeatingStep(temperature_setpoint=973),
            SAPLDDepositionStep(samples=[old_sample], target=target),
        ],
    )
    logbook = SAPLDLogbook(
        load_recipe=RecipeLoader(recipe=recipe, sample=new_sample, apply_recipe=True)
    )
    _normalize(logbook)

    assert [type(step) for step in logbook.steps] == [
        SAPLDHeatingStep,
        SAPLDDepositionStep,
    ]
    assert logbook.steps[1].samples == [new_sample]
    assert recipe.steps[1].samples == [old_sample]
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


def test_recipe_without_sample_uses_all_samples_of_the_run():
    first, second = Sample(sample_id='a'), Sample(sample_id='b')
    recipe = SAPLDLogbook(steps=[SAPLDDepositionStep()])
    logbook = SAPLDLogbook(
        samples=[SampleInRun(sample=first), SampleInRun(sample=second)],
        load_recipe=RecipeLoader(recipe=recipe, apply_recipe=True),
    )
    _normalize(logbook)
    assert logbook.steps[0].samples == [first, second]


# Samples


def test_new_samples_get_id_name_and_uuid():
    logbook = LAPLDLogbook(
        datetime='2026-10-22T09:15:00+00:00',
        samples=[
            SampleInRun(
                origin='New sample',
                substrate='SrTiO3 10x10 mm',
                layers=[Layer(material='YSZ', thickness=2e-8)],
            ),
            SampleInRun(origin='Existing sample', sample=Sample(sample_id='old')),
            SampleInRun(origin='External sample', substrate='FTO'),
        ],
    )
    _normalize(logbook)
    new, existing, external = logbook.samples
    assert new.sample_id == 'LA-PLD_2026-10-22_09:15_S01'
    assert new.name == 'SrTiO3_YSZ-20nm'
    assert len(new.sample_uuid) == UUID_LENGTH
    assert existing.sample_id == 'old'
    assert external.sample_id == 'LA-PLD_2026-10-22_09:15_S02'


def test_given_sample_id_is_kept():
    logbook = SAPLDLogbook(
        datetime='2026-10-22T09:15:00+00:00',
        samples=[SampleInRun(origin='New sample', sample_id='SA-PLD_x_S01')],
    )
    _normalize(logbook)
    assert logbook.samples[0].sample_id == 'SA-PLD_x_S01'


def test_existing_sample_must_be_selected():
    logbook = SAPLDLogbook(samples=[SampleInRun(origin='Existing sample')])
    _, records = _normalize(logbook)
    assert any('existing sample' in message for _, message in records)


def test_sample_entry():
    sample = Sample(
        sample_id='SA-PLD_2026-10-22_09:15_S01',
        substrate='Si 1" with flat',
        layers=[Layer(material='SrTiO3', thickness=2e-8), Layer(material='YSZ')],
    )
    archive, _ = _normalize(sample)
    assert sample.name == 'Si_SrTiO3-20nm_YSZ'
    assert sample.lab_id == sample.sample_id
    assert sample.substrate_material == 'Si'
    assert sample.substrate_size == '1" with flat'
    assert archive.metadata.entry_name == sample.sample_id
    assert len(sample.sample_uuid) == UUID_LENGTH


def test_sample_name():
    assert sample_name('FTO', []) == 'FTO'
    assert sample_name('Other', [('YSZ', 2.5)], 'MgO') == 'MgO_YSZ-2.5nm'
    assert sample_name(None, [('YSZ', 2.5)]) is None


def test_sa_deposition_records_samples_and_stage_scan():
    step = SAPLDDepositionStep(substrate_stage_scan=True)
    _normalize_section(step)
    assert step.substrate_scan is not None
    assert {'scan_width_x', 'scan_speed_y'} <= set(
        step.substrate_scan.m_def.all_quantities
    )
    assert 'samples' in step.m_def.all_quantities


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


def test_in_situ_technique_awaits_data_until_a_file_is_added():
    rheed = RHEED()
    records = _normalize_section(rheed)
    assert rheed.data_status == 'awaiting data'
    assert any('no data file' in message for _, message in records)
    rheed.pattern_export_file = 'pld_files/run/pattern.png'
    assert not _normalize_section(rheed)
    assert rheed.data_status == 'complete'


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
    assert deposition.valve_position_fixed is True
    assert logbook.samples[0].sample_id == f'{system}_2026-10-22_09:00_S01'
    heating = next(s for s in logbook.steps if 'Heating' in s.m_def.name)
    assert heating.heater_output == pytest.approx(35)


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


def test_incomplete_samples_are_not_reported_as_duplicates():
    logbook = SAPLDLogbook(samples=[SampleInRun(), SampleInRun()])
    _, records = _normalize(logbook)
    assert not any('listed twice' in message for _, message in records)


def test_duplicate_sample_is_reported():
    logbook = SAPLDLogbook(
        samples=[SampleInRun(sample_id='x'), SampleInRun(sample_id='x')]
    )
    _, records = _normalize(logbook)
    assert any('listed twice' in message for _, message in records)


def test_operator_is_recorded():
    logbook = SAPLDLogbook(operator_name='Ada', operator_email='ada@example.org')
    assert logbook.m_to_dict()['operator_email'] == 'ada@example.org'


def test_pvd_system_is_stored_on_save():
    logbook = LAPLDLogbook()
    assert not logbook.m_is_set(LAPLDLogbook.m_def.all_quantities['pvd_system'])
    archive, _ = _normalize(logbook)
    assert logbook.m_is_set(LAPLDLogbook.m_def.all_quantities['pvd_system'])
    assert archive.data.m_to_dict()['pvd_system'] == 'LA-PLD'
