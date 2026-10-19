from nomad.datamodel import EntryArchive, ArchiveSection
from nomad_material_processing.general import (
    Substrate as MaterialProcessingSubstrate,
)
from nomad_material_processing.general import (
    ThinFilm as MaterialProcessingThinFilm,
)
from nomad_material_processing.general import (
    ThinFilmStack as MaterialProcessingThinFilmStack,
)
from nomad_material_processing.vapor_deposition.general import (
    SampleParameters as MaterialProcessingSampleParameters,
)
from structlog.testing import CapturingLogger

import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.base_sections import Entity, ProcessStep
from differ_pld4e_schemas.environment import ChamberEnvironment
from differ_pld4e_schemas.normalizers import normalize_deposition
from differ_pld4e_schemas.sample_parameters import SampleParameters
from differ_pld4e_schemas.source import SputterDepositionSource
from differ_pld4e_schemas.sputter_deposition import Deposition, SputterDepositionStep
from differ_pld4e_schemas.substrate import Substrate
from differ_pld4e_schemas.target import Target
from differ_pld4e_schemas.thin_film import ThinFilm, ThinFilmStack

EXPECTED_VOLTAGE = 350
EXPECTED_LAYER_THICKNESS = 5e-8


def test_schema_sections_instantiate():
    assert issubclass(Substrate, MaterialProcessingSubstrate)
    assert issubclass(ThinFilm, MaterialProcessingThinFilm)
    assert issubclass(ThinFilmStack, MaterialProcessingThinFilmStack)
    assert issubclass(SampleParameters, MaterialProcessingSampleParameters)

    assert Substrate(material='Si', rotation_speed=20).material == 'Si'
    assert (
        Substrate(material='Si', datetime='2024-01-01T00:00:00Z').datetime is not None
    )
    assert Target(material='Ti').material == 'Ti'
    assert (
        SputterDepositionSource(cathode_voltage=350).cathode_voltage.to('V').magnitude
        == EXPECTED_VOLTAGE
    )
    assert SampleParameters(sample_id='SUB-1').sample_id == 'SUB-1'
    assert (
        ThinFilm(material='Au', thickness=EXPECTED_LAYER_THICKNESS)
        .thickness.to('m')
        .magnitude
        == EXPECTED_LAYER_THICKNESS
    )
    assert ThinFilmStack(stack_name='Au/Si').stack_name == 'Au/Si'
    assert SputterDepositionStep(name='step', sputtering_technique='DC').name == 'step'


def test_inherited_sections_are_owned_by_plugin_package():
    assert Substrate.m_def.m_parent.name.startswith('differ_pld4e_schemas')
    assert SputterDepositionStep.m_def.m_parent.name.startswith('differ_pld4e_schemas')
    assert Entity.m_def.m_parent.name.startswith('differ_pld4e_schemas')
    assert ProcessStep.m_def.m_parent.name.startswith('differ_pld4e_schemas')
    assert 'name' in Substrate.m_def.all_quantities
    assert 'duration' in SputterDepositionStep.m_def.all_quantities


def test_data_sections_are_archive_sections():
    for section in (
        SampleParameters,
        SputterDepositionSource,
        Target,
        ChamberEnvironment,
    ):
        assert issubclass(section, ArchiveSection)


def test_normalization_builds_ordered_stack():
    first_layer = ThinFilm(layer_name='Ti', material='Ti', thickness=2e-8)
    second_layer = ThinFilm(layer_name='Pt', material='Pt', thickness=3e-8)
    deposition = Deposition(
        substrate=Substrate(sample_id='SUB-1', material='Si'),
        steps=[
            SputterDepositionStep(name='adhesion', deposited_layer=first_layer),
            SputterDepositionStep(name='electrode', deposited_layer=second_layer),
        ],
    )

    normalize_deposition(deposition, EntryArchive(), CapturingLogger())

    assert deposition.resulting_stack is not None
    assert [
        layer.reference.material for layer in deposition.resulting_stack.layers
    ] == [
        'Ti',
        'Pt',
    ]
    assert deposition.resulting_stack.layers[0].reference is not first_layer
    assert (
        deposition.resulting_stack.layers[0].reference.deposition_step_reference
        == 'adhesion'
    )
    assert (
        deposition.resulting_stack.total_thickness.to('m').magnitude
        == EXPECTED_LAYER_THICKNESS
    )


def test_validation_reports_errors_and_warnings():
    logger = CapturingLogger()
    deposition = Deposition(
        substrate=Substrate(sample_id='SUB-1'),
        steps=[
            SputterDepositionStep(
                deposition_time=0,
                sputtering_technique='DC',
                source=SputterDepositionSource(target=Target(material='Ti')),
                chamber_environment=ChamberEnvironment(
                    base_pressure=0.5, working_pressure=0.1
                ),
                deposited_layer=ThinFilm(material='Au', thickness=-1),
            )
        ],
    )

    normalize_deposition(deposition, EntryArchive(), logger)

    records = [(call[0], call[1][0]) for call in logger.calls]
    assert ('error', 'Deposition time must be greater than 0.') in records
    assert ('error', 'Film thickness cannot be negative.') in records
    assert (
        'warning',
        'Working pressure is lower than base pressure. Please check logs.',
    ) in records
    assert any(
        level == 'warning'
        and 'Target material (Ti) differs from film material (Au)' in message
        for level, message in records
    )
