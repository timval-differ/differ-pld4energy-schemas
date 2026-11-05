"""
The entries are native NOMAD sections, so NOMAD's search finds them: these tests
run NOMAD's full normalization and check what ends up in `results`.
"""

from datetime import datetime, timezone

import pytest
from nomad.client import normalize_all
from nomad.datamodel import EntryArchive, EntryMetadata

import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.composition import parse_formula
from differ_pld4e_schemas.gas import BackgroundGas
from differ_pld4e_schemas.in_situ import (
    RHEED,
    InSituTechniques,
    InSituTechniquesEntry,
    MeasuredSample,
)
from differ_pld4e_schemas.laser import LaserParameters
from differ_pld4e_schemas.pld_deposition import (
    SAPLDDepositionStep,
    SAPLDHeatingStep,
    SAPLDLogbook,
    SelectedTarget,
)
from differ_pld4e_schemas.sample import Layer, Sample, SampleInRun, SubstrateType
from differ_pld4e_schemas.sps_deposition import (
    SPSLogbook,
    SPSSputteringStep,
    SputterPlasma,
)
from differ_pld4e_schemas.target import PLDTarget, SputterTarget

START = datetime(2026, 11, 5, 9, 15, tzinfo=timezone.utc)
PULSES = 3000
SUBSTRATE_TEMPERATURE = 973.0
PRESSURE = 10.0
POWER = 100.0


def normalized(data):
    archive = EntryArchive(data=data, metadata=EntryMetadata())
    normalize_all(archive)
    return archive


def elements(archive):
    material = archive.results.material if archive.results else None
    return sorted(material.elements) if material and material.elements else []


@pytest.fixture
def ysz():
    target = PLDTarget(
        material='8YSZ', chemical_formula='(Y2O3)0.08(ZrO2)0.92', radius=0.0125
    )
    normalized(target)
    return target


@pytest.fixture
def sto():
    substrate = SubstrateType(
        material='SrTiO3', chemical_formula='SrTiO3', size='10x10 mm'
    )
    normalized(substrate)
    return substrate


@pytest.mark.parametrize(
    'text, valid',
    [
        ('SrTiO3', True),
        ('(Y2O3)0.08(ZrO2)0.92', True),
        ('La0.7Sr0.3MnO3', True),
        ('8YSZ', False),  # read as Y, S and an unknown Z
        ('STO', False),
        ('', False),
        (None, False),
    ],
)
def test_lab_names_are_not_formulas(text, valid):
    assert (parse_formula(text) is not None) is valid


def test_target_is_found_by_elements_and_formula(ysz):
    archive = normalized(ysz)
    assert elements(archive) == ['O', 'Y', 'Zr']
    assert archive.results.material.chemical_formula_hill == 'O52Y4Zr23'
    assert archive.metadata.entry_name == '8YSZ'


def test_target_with_a_lab_name_as_formula_gets_no_elements():
    target = PLDTarget(material='YSZ', chemical_formula='8YSZ', radius=0.0125)
    archive = normalized(target)
    assert elements(archive) == []
    assert not target.elemental_composition


def test_substrate_is_found_by_elements(sto):
    archive = normalized(sto)
    assert elements(archive) == ['O', 'Sr', 'Ti']
    assert archive.results.material.chemical_formula_reduced == 'O3SrTi'


def test_sample_has_the_elements_of_substrate_and_films(ysz, sto):
    sample = Sample(
        sample_id='SA-PLD_2026-11-05_09:15_S01',
        substrate=sto,
        layers=[Layer(target=ysz, thickness=2e-8)],
    )
    archive = normalized(sample)
    assert elements(archive) == ['O', 'Sr', 'Ti', 'Y', 'Zr']
    assert sample.layers[0].name == '8YSZ'
    assert archive.metadata.entry_name == 'SA-PLD_2026-11-05_09:15_S01'


def test_pld_logbook_is_a_native_pulsed_laser_deposition(ysz, sto):
    logbook = SAPLDLogbook(
        datetime=START,
        targets=[SelectedTarget(target_number=1, target=ysz)],
        samples=[
            SampleInRun(origin='New sample', substrate=sto, layers=[Layer(target=ysz)])
        ],
        steps=[
            SAPLDHeatingStep(
                temperature_setpoint=SUBSTRATE_TEMPERATURE,
                pressure=PRESSURE,
                background_gases=[BackgroundGas(gas='O2', flow_setpoint=5)],
            ),
            # Its target is filled in by the logbook: the only target of the run.
            SAPLDDepositionStep(
                substrate_temperature=SUBSTRATE_TEMPERATURE,
                laser=LaserParameters(number_of_laser_pulses=PULSES),
            ),
        ],
        in_situ_measurements=[InSituTechniques(rheed=[RHEED()])],
    )
    archive = normalized(logbook)
    assert logbook.name == 'SA-PLD 2026-11-05 09:15'
    methods = archive.results.eln.methods
    assert {'Pulsed Laser Deposition', 'In-situ diagnostics', 'RHEED'} <= set(methods)
    # The films grown in the run.
    assert elements(archive) == ['O', 'Y', 'Zr']
    heating, deposition = logbook.steps
    assert heating.environment.pressure.set_value.magnitude[0] == PRESSURE
    assert heating.environment.gas_flow[0].gas.name == 'O2'
    assert heating.sample_parameters[0].substrate_temperature is not None
    assert deposition.creates_new_thin_film
    source = deposition.sources[0]
    assert source.material[0].system is ysz
    assert source.vapor_source.pulses == PULSES
    # The in-situ measurement does not take over the workflow of the run.
    assert archive.workflow2.name == logbook.name
    assert not archive.workflow2.inputs


def test_sps_logbook_is_a_native_sputter_deposition():
    ta = SputterTarget(material='Ta', chemical_formula='Ta', diameter=0.0508)
    logbook = SPSLogbook(
        datetime=START,
        steps=[SPSSputteringStep(target=ta, plasma=SputterPlasma(power=POWER))],
    )
    archive = normalized(logbook)
    assert 'Sputter Deposition' in archive.results.eln.methods
    source = logbook.steps[0].sources[0]
    assert source.material[0].name == 'Ta'
    assert source.vapor_source.power.set_value.magnitude[0] == POWER


def test_in_situ_entry_lists_its_techniques_as_methods(sto):
    sample = Sample(sample_id='S1', substrate=sto)
    entry = InSituTechniquesEntry(
        samples=[MeasuredSample(reference=sample)],
        rheed=[RHEED(pattern_export_files=['a.png'])],
    )
    archive = normalized(entry)
    assert entry.name == 'RHEED'
    assert {'In-situ diagnostics', 'RHEED'} <= set(archive.results.eln.methods)
    assert [link.section for link in archive.workflow2.inputs] == [sample]
