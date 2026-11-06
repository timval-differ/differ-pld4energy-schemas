from pathlib import Path

import pytest
import yaml
from nomad.datamodel import EntryArchive, EntryMetadata
from structlog.testing import CapturingLogger

import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.pld_deposition import SAPLDHeatingStep, SAPLDStep
from differ_pld4e_schemas.sample import Layer, SampleInRun, SubstrateType
from differ_pld4e_schemas.sps_deposition import (
    CARRIERS,
    FIXED_STAGE,
    SelectedSputterTarget,
    SPSCoolDownStep,
    SPSHeatingStep,
    SPSLogbook,
    SPSPreSputteringStep,
    SPSSputteringStep,
    SPSStep,
    SputterPlasma,
)
from differ_pld4e_schemas.target import PLDTarget, SputterTarget

INCH = 0.0254
TA = SputterTarget(material='Ta', diameter=2 * INCH)
TI = SputterTarget(material='Ti', diameter=2 * INCH)
SI = SubstrateType(material='Si', size='4"')
SPS_STEPS = (SPSPreSputteringStep, SPSHeatingStep, SPSSputteringStep, SPSCoolDownStep)


def _normalize(data):
    archive = EntryArchive(data=data, metadata=EntryMetadata())
    logger = CapturingLogger()
    data.normalize(archive, logger)
    return archive, [(call[0], call[1][0]) for call in logger.calls]


def _offered_steps(logbook):
    steps = logbook.m_def.all_sub_sections['steps'].sub_section
    return {steps, *steps.all_inheriting_sections}


# Targets


def test_sputter_target_entry_is_named_after_material():
    target = SputterTarget(material='NiTi', diameter=4 * INCH)
    archive, _ = _normalize(target)
    assert target.name == 'NiTi'
    assert archive.metadata.entry_name == 'NiTi'
    assert target.in_stock is True
    assert target.diameter.to('inch').magnitude == pytest.approx(4)


def test_sputter_and_pld_targets_are_separate_databases():
    assert not isinstance(TA, PLDTarget)
    assert not isinstance(PLDTarget(), SputterTarget)


def test_selected_target_copies_material_and_diameter():
    selected = SelectedSputterTarget(target_number=1, target=TA)
    _normalize(SPSLogbook(targets=[selected]))
    assert selected.material == 'Ta'
    assert selected.diameter.to('inch').magnitude == pytest.approx(2)


def test_target_that_does_not_fit_its_position_is_reported():
    logbook = SPSLogbook(targets=[SelectedSputterTarget(target_number=3, target=TA)])
    _, records = _normalize(logbook)
    assert ('warning', 'Target 3 takes 4" targets, but Ta is 2".') in records


def test_target_number_outside_the_positions_is_reported():
    logbook = SPSLogbook(targets=[SelectedSputterTarget(target_number=4, target=TA)])
    _, records = _normalize(logbook)
    assert any('not a position' in message for _, message in records)


def test_duplicate_targets_and_numbers_are_reported():
    logbook = SPSLogbook(
        targets=[
            SelectedSputterTarget(target_number=1, target=TA),
            SelectedSputterTarget(target_number=1, target=TA),
        ]
    )
    _, records = _normalize(logbook)
    assert any(level == 'error' and 'more than once' in m for level, m in records)
    assert any('used twice' in message for _, message in records)


def test_step_takes_its_target_number_from_the_target_details():
    logbook = SPSLogbook(
        targets=[
            SelectedSputterTarget(target_number=1, target=TA),
            SelectedSputterTarget(target_number=2, target=TI),
        ],
        steps=[SPSSputteringStep(target=TI), SPSHeatingStep()],
    )
    _normalize(logbook)
    assert logbook.steps[0].target_number == 2  # noqa: PLR2004


def test_only_target_is_used_by_default():
    logbook = SPSLogbook(
        targets=[SelectedSputterTarget(target_number=1, target=TA)],
        steps=[SPSPreSputteringStep()],
    )
    _normalize(logbook)
    assert logbook.steps[0].target is TA
    assert logbook.steps[0].target_number == 1


# System details and steps


def test_logbook_stores_its_system():
    logbook = SPSLogbook()
    _normalize(logbook)
    assert logbook.pvd_system == 'SPS'
    assert logbook.datetime is not None


def test_mask_only_with_the_fixed_stage():
    assert FIXED_STAGE in CARRIERS
    _, records = _normalize(SPSLogbook(substrate_carrier=FIXED_STAGE, mask_used=True))
    assert not any('mask' in message for _, message in records)
    _, records = _normalize(SPSLogbook(substrate_carrier=CARRIERS[0], mask_used=True))
    assert any('mask' in message for _, message in records)


def test_sps_logbook_offers_only_sps_steps():
    offered = _offered_steps(SPSLogbook)
    assert {step.m_def for step in SPS_STEPS} <= offered
    assert SAPLDHeatingStep.m_def not in offered
    assert not any(issubclass(s.section_cls, SAPLDStep) for s in offered)


@pytest.mark.parametrize('step', SPS_STEPS)
def test_steps_are_sps_steps_with_gases(step):
    assert issubclass(step, SPSStep)
    assert 'background_gases' in step.m_def.all_sub_sections
    assert 'pressure' in step.m_def.all_quantities


def test_sputter_steps_record_the_plasma():
    for step in (SPSPreSputteringStep, SPSSputteringStep):
        assert step.m_def.all_sub_sections['plasma'].sub_section == (
            SputterPlasma.m_def
        )
    plasma = SputterPlasma(plasma_type='DC+RF', load_capacitance=1.2e-9, current=0.2)
    assert plasma.load_capacitance.to('nF').magnitude == pytest.approx(1.2)
    assert plasma.current.to('mA').magnitude == pytest.approx(200)


def test_power_ramps_are_rates():
    step = SPSPreSputteringStep(ramp_up_rate=2 / 60)
    assert step.ramp_up_rate.to('W/minute').magnitude == pytest.approx(2)
    assert 'ramp_down_rate' in SPSSputteringStep.m_def.all_quantities


def test_sputtering_step_times_are_in_minutes():
    for step, name in (
        (SPSPreSputteringStep, 'pre_sputter_time'),
        (SPSSputteringStep, 'sputter_time'),
    ):
        quantity = step.m_def.all_quantities[name]
        assert quantity.m_annotations['eln'].defaultDisplayUnit == 'minute'


# Samples


def test_new_samples_get_sps_ids_and_names():
    logbook = SPSLogbook(
        datetime='2026-10-22T09:15:00+00:00',
        samples=[
            SampleInRun(
                origin='New sample',
                substrate=SI,
                layers=[
                    Layer(target=TA, thickness=5e-8),
                    Layer(target=TI, thickness=1e-8),
                ],
            ),
        ],
    )
    _normalize(logbook)
    sample = logbook.samples[0]
    assert sample.sample_id == 'SPS_2026-10-22_09:15_S01'
    assert sample.name == 'Si_Ta-50nm_Ti-10nm'


# Example entry


def test_example_logbook():
    with open(Path(__file__).resolve().parent / 'data' / 'example_sps.archive.yaml') as file:
        archive = EntryArchive.m_from_dict(yaml.safe_load(file))
    archive.metadata = EntryMetadata()
    logbook = archive.data
    # Like NOMAD processing: normalize sub-sections before their parents.
    for section in reversed(list(logbook.m_all_contents(include_self=True))):
        section.normalize(archive, CapturingLogger())
    assert isinstance(logbook, SPSLogbook)
    assert logbook.pvd_system == 'SPS'
    assert [type(step) for step in logbook.steps] == [
        SPSPreSputteringStep,
        SPSHeatingStep,
        SPSSputteringStep,
        SPSSputteringStep,
        SPSCoolDownStep,
    ]
    sputtering = logbook.steps[2]
    assert sputtering.plasma.current.to('mA').magnitude == pytest.approx(260)
    assert sputtering.sputter_time.to('minute').magnitude == pytest.approx(20)
    assert sputtering.heater_rotation.to('rpm').magnitude == pytest.approx(10)
    assert logbook.samples[0].name == 'Si_Ta-50nm_Ti-10nm'
