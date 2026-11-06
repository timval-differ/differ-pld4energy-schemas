from pathlib import Path

import numpy as np
import pytest
import yaml
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.context import ClientContext
from nomad.datamodel.data import EntryData
from nomad.normalizing.metainfo import MetainfoNormalizer
from structlog.testing import CapturingLogger, capture_logs

import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.gas import BackgroundGas
from differ_pld4e_schemas.in_situ import (
    LAEDS,
    MIC,
    RHEED,
    InSituTechniques,
    InSituTechniquesEntry,
    block_mean,
    block_size,
    energy_axis,
    read_columns,
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
from differ_pld4e_schemas.sample import (
    Layer,
    Sample,
    SampleInRun,
    SubstrateType,
    sample_name,
)
from differ_pld4e_schemas.sps_deposition import SPSSputteringStep, SPSStep
from differ_pld4e_schemas.target import CIRCULAR, RECTANGULAR, PLDTarget

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


YSZ_FORMULA = '(Y2O3)0.08(ZrO2)0.92'


def test_circular_target_diameter_follows_from_radius():
    target = PLDTarget(
        material='YSZ', chemical_formula=YSZ_FORMULA, radius=0.0125, lab_id='T-042'
    )
    _, records = _normalize(target)
    assert target.shape == CIRCULAR
    assert target.diameter.to('m').magnitude == pytest.approx(0.025)
    assert not records


def test_rectangular_target_needs_length_and_width():
    target = PLDTarget(
        material='YSZ', chemical_formula=YSZ_FORMULA, shape=RECTANGULAR, diameter=0.025
    )
    _, records = _normalize(target)
    assert target.diameter is None
    assert ('warning', 'Enter the length and width of a rectangular target.') in records
    target = PLDTarget(
        material='YSZ',
        chemical_formula=YSZ_FORMULA,
        shape=RECTANGULAR,
        length=0.03,
        width=0.02,
    )
    assert not _normalize(target)[1]


def test_circular_target_needs_radius():
    _, records = _normalize(PLDTarget(material='YSZ'))
    assert ('warning', 'Enter the radius of a circular target.') in records


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
        'target_select',
        'scan_axis',
        'area',
        'scan_width_x',
        'scan_width_y',
        'spot_width',
        'spot_height',
        'scan_speed_x',
        'scan_speed_y',
        'target_size',
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
    assert SPSSputteringStep.m_def not in offered
    assert not any(
        section in offered for section in SPSStep.m_def.all_inheriting_sections
    )
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
        samples=[SampleInRun(reference=first), SampleInRun(reference=second)],
        load_recipe=RecipeLoader(recipe=recipe, apply_recipe=True),
    )
    _normalize(logbook)
    assert logbook.steps[0].samples == [first, second]


# Samples


STO = SubstrateType(material='SrTiO3', size='10x10 mm')
YSZ = PLDTarget(material='YSZ')


def test_new_samples_get_id_name_and_uuid():
    logbook = LAPLDLogbook(
        datetime='2026-10-22T09:15:00+00:00',
        samples=[
            SampleInRun(
                origin='New sample',
                substrate=STO,
                layers=[Layer(target=YSZ, thickness=2e-8)],
            ),
            SampleInRun(origin='Existing sample', reference=Sample(sample_id='old')),
            SampleInRun(origin='External sample', substrate_details='FTO'),
        ],
    )
    _normalize(logbook)
    new, existing, external = logbook.samples
    assert new.sample_id == 'LA-PLD_2026-10-22_09:15_S01'
    assert new.substrate_material == 'SrTiO3'
    assert new.layers[0].material == 'YSZ'
    assert new.name == 'SrTiO3_YSZ-20nm'
    assert len(new.sample_uuid) == UUID_LENGTH
    assert existing.sample_id == 'old'
    assert external.sample_id == 'LA-PLD_2026-10-22_09:15_S02'
    assert external.name == 'FTO'


def test_external_sample_films_come_first():
    item = SampleInRun(
        origin='External sample',
        sample_id='x',
        substrate_details='MgO',
        prior_layers=[Layer(material='SrRuO3', thickness=1e-8)],
        layers=[Layer(target=YSZ, thickness=2e-8)],
    )
    logbook = LAPLDLogbook(datetime='2026-10-22T09:15:00+00:00', samples=[item])
    _normalize(logbook)
    assert item.name == 'MgO_SrRuO3-10nm_YSZ-20nm'
    sample = item.to_sample('LA-PLD', None)
    assert [layer.material for layer in sample.layers] == ['SrRuO3', 'YSZ']


@pytest.mark.parametrize('entry', (PLDTarget, SubstrateType))
def test_database_entries_are_in_stock_until_switched_off(entry):
    assert entry().in_stock is True
    assert entry(in_stock=False).in_stock is False


def test_substrate_type_entry():
    substrate = SubstrateType(material='Si', size='1" with flat')
    archive, _ = _normalize(substrate)
    assert substrate.name == 'Si 1" with flat'
    assert archive.metadata.entry_name == 'Si 1" with flat'


def test_film_material_comes_from_its_target():
    layer = Layer(target=YSZ)
    _normalize_section(layer)
    assert layer.material == 'YSZ'
    given = Layer(target=YSZ, material='8YSZ')
    _normalize_section(given)
    assert given.material == '8YSZ'


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
        substrate=SubstrateType(material='Si', size='1" with flat'),
        layers=[Layer(material='SrTiO3', thickness=2e-8), Layer(target=YSZ)],
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
    assert sample_name('MgO', [('YSZ', 2.5), (None, 3)]) == 'MgO_YSZ-2.5nm'
    assert sample_name(None, [('YSZ', 2.5)]) is None
    assert sample_name('MgO', [('YSZ', None, 1500), ('STO', 5, None)]) == (
        'MgO_YSZ-1500p_STO-5nm'
    )


def test_sa_pld_steps_have_laser_heating():
    assert SAPLDDepositionStep().laser_output_limitation == pytest.approx(50)
    assert SAPLDAnnealingStep().laser_output_limitation == pytest.approx(50)
    quantities = SAPLDHeatingStep.m_def.all_quantities
    assert {
        'heating_mode',
        'power_setpoint',
        'ramp_on',
        'power_ramp_rate',
        'fix_output',
        'drift_compensation',
    } <= set(quantities)
    assert 'supply_voltage' not in quantities


def test_la_pld_steps_have_the_main_heater_power_supply():
    quantities = LAPLDDepositionStep.m_def.all_quantities
    assert {
        'supply_voltage',
        'supply_current',
        'actual_voltage',
        'actual_current',
        'fix_output',
        'drift_compensation',
    } <= set(quantities)
    assert 'heating_mode' not in quantities
    assert 'laser_output_limitation' not in LAPLDAnnealingStep.m_def.all_quantities
    assert LAPLDDepositionStep().drift_compensation is False


def test_target_number_outside_the_positions_is_reported():
    logbook = SAPLDLogbook(targets=[SelectedTarget(target_number=7, target=YSZ)])
    _, records = _normalize(logbook)
    assert any('not a position' in message for _, message in records)


def test_sa_deposition_records_samples_and_heater_scan():
    step = SAPLDDepositionStep()
    _normalize_section(step)
    assert step.polar_scan is not None
    assert 'substrate_scan' not in step.m_def.all_sub_sections
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
    assert step.heater_scan_axis == 'X'
    assert step.heater_size == '25mm / 1"'
    assert step.cartesian_scan.area == 'None'
    assert {
        'width_x',
        'height_z',
        'spot_width',
        'spot_height',
        'x_offset',
        'z_offset',
        'scan_speed_x',
        'scan_speed_z',
    } <= set(step.cartesian_scan.m_def.all_quantities)


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
    rheed.pattern_export_files = ['pld_files/run/a.png', 'pld_files/run/b.png']
    assert not _normalize_section(rheed)
    assert rheed.data_status == 'complete'


def test_in_situ_techniques_are_top_level():
    assert 'in_situ_measurements' in SAPLDLogbook.m_def.all_sub_sections
    assert 'in_situ_measurements' not in SAPLDDepositionStep.m_def.all_sub_sections
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


# Exported RHEED and MIC data

DATA_DIR = Path(__file__).resolve().parent / 'data'
RAW_DATA = str(DATA_DIR / 'raw_data')
RHEED_EXPORT = 'RHEED/step1.txt'
MIC_EXPORT = 'MIC/EZ-CURVE_dated_09_October_2026_timestamped_11h_51m_13s.csv'
MIC_ROWS = 300


def _normalize_with_files(data, local_dir=RAW_DATA):
    archive = EntryArchive(
        data=data,
        metadata=EntryMetadata(),
        m_context=ClientContext(local_dir=local_dir),
    )
    with capture_logs() as logs:
        MetainfoNormalizer().normalize(archive)
    return [log['event'] for log in logs]


@pytest.fixture
def mic_dir(tmp_path):
    """The header and first rows of the MIC example, which is large."""
    with open(Path(RAW_DATA) / MIC_EXPORT) as export:
        lines = [export.readline() for _ in range(MIC_ROWS + 1)]
    (tmp_path / 'MIC').mkdir()
    (tmp_path / MIC_EXPORT).write_text(''.join(lines))
    (tmp_path / 'RHEED').mkdir()
    (tmp_path / RHEED_EXPORT).write_text(
        open(Path(RAW_DATA) / RHEED_EXPORT).read()
    )
    return str(tmp_path)


def test_read_columns():
    header, columns = read_columns(['a;b (s)', '1;2', '', '3;4'], ';')
    assert header == ['a', 'b (s)']
    assert np.allclose(columns, [[1, 3], [2, 4]])
    header, columns = read_columns(['0.0\t1.0\t2.0\n', '0.1 1.5 2.5'])
    assert header is None
    assert columns.shape == (3, 2)
    with pytest.raises(ValueError, match='columns instead of'):
        read_columns(['1 2', '1 2 3'])
    with pytest.raises(ValueError, match='not numbers'):
        read_columns(['1 2', 'x y'])
    with pytest.raises(ValueError):
        read_columns(['only a header'])


def test_block_mean():
    assert block_size(10, 5) == 2  # noqa: PLR2004
    assert block_size(11, 5) == 3  # noqa: PLR2004
    assert block_size(3, 5) == 1
    assert np.allclose(block_mean(np.array([[1, 3, 5, 7, 9]]), 2), [[2, 6, 9]])


def test_rheed_reads_roi_intensity_export():
    rheed = RHEED(roi_intensity_export_files=[RHEED_EXPORT])
    _normalize_with_files(InSituTechniquesEntry(rheed=[rheed]))
    (roi_map,) = rheed.roi_intensities
    assert roi_map.averaged_samples == 1
    assert len(roi_map.time) == 2024  # noqa: PLR2004
    assert roi_map.time[-1].to('s').magnitude == pytest.approx(214.621)
    assert [roi.roi for roi in roi_map.rois] == [1, 2, 3]
    assert roi_map.rois[0].intensity[0] == pytest.approx(98.99878)
    assert [f.label for f in rheed.figures] == ['RHEED ROI intensity: step1.txt']
    assert len(rheed.figures[0].figure['data']) == 3  # noqa: PLR2004


def test_mic_reads_curvature_export(mic_dir):
    mic = MIC(export_files=[MIC_EXPORT])
    _normalize_with_files(InSituTechniquesEntry(mic=[mic]), mic_dir)
    (data,) = mic.curvature_data
    assert len(data.time) == MIC_ROWS
    assert data.time[0].to('s').magnitude == pytest.approx(0.01)
    assert data.sagittal_curvature[0].to('1/km').magnitude == pytest.approx(
        14.6924654976594
    )
    assert data.tangential_stress_thickness[0].to('GPa*nm').magnitude == (
        pytest.approx(0.870112194638309)
    )
    assert data.sagittal_stress_thickness_rate is not None
    assert data.tangential_bow[0] == pytest.approx(-0.0287423133850098)
    assert [f.label.split(':')[0] for f in mic.figures] == [
        'MIC stress x thickness',
        'MIC curvature',
    ]


def test_long_exports_are_averaged(tmp_path):
    (tmp_path / 'long.txt').write_text(
        '\n'.join(f'{i * 0.1} {i} {2 * i}' for i in range(12000))
    )
    rheed = RHEED(roi_intensity_export_files=['long.txt'])
    _normalize_with_files(InSituTechniquesEntry(rheed=[rheed]), str(tmp_path))
    (roi_map,) = rheed.roi_intensities
    assert roi_map.averaged_samples == 3  # noqa: PLR2004
    assert len(roi_map.time) == 4000  # noqa: PLR2004
    assert roi_map.rois[0].intensity[0] == pytest.approx(1)


def test_unreadable_export_is_reported():
    rheed = RHEED(roi_intensity_export_files=['RHEED/missing.txt'])
    events = _normalize_with_files(InSituTechniquesEntry(rheed=[rheed]))
    assert any('could not read RHEED/missing.txt' in event for event in events)
    assert not rheed.roi_intensities
    assert rheed.data_status == 'complete'


def test_export_figures_show_on_the_entry(mic_dir):
    def measurement():
        return InSituTechniques(
            rheed=[RHEED(roi_intensity_export_files=[RHEED_EXPORT])],
            mic=[MIC(export_files=[MIC_EXPORT])],
        )

    entry = InSituTechniquesEntry(**measurement().m_to_dict())
    _normalize_with_files(entry, mic_dir)
    assert len(entry.figures) == 3  # noqa: PLR2004
    logbook = SAPLDLogbook(in_situ_measurements=[measurement(), measurement()])
    _normalize_with_files(logbook, mic_dir)
    labels = [figure.label for figure in logbook.figures]
    assert len(labels) == 6  # noqa: PLR2004
    assert labels[0] == 'Measurement 1: RHEED ROI intensity: step1.txt'
    assert labels[-1].startswith('Measurement 2: MIC curvature')


# Example entries


@pytest.mark.parametrize(
    'file_name, system',
    (
        ('example_sa_pld.archive.yaml', 'SA-PLD'),
        ('example_la_pld.archive.yaml', 'LA-PLD'),
    ),
)
def test_example_logbooks(file_name, system):
    with open(DATA_DIR / file_name) as archive_file:
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
    from differ_pld4e_schemas.references import (
        absolute_reference as _absolute_reference,
    )

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
