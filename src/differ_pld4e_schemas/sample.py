"""
Samples, independent of the system they are made or processed in.

A substrate is the template a film is grown on; a sample is the substrate with
the films grown on it. Every run (a PLD logbook now, a sputter run later) starts
by listing the samples it makes or processes, with `SampleRun`.

The kinds of substrate in use (e.g. SrTiO3 10x10 mm) are kept in a database of
`SubstrateType` entries, like the targets, so new ones can be added without a
code change. A film refers to the target it is grown from, which gives its
material.

The sections are native NOMAD ones (nomad-material-processing): a substrate type
is a `CrystallineSubstrate`, a film a `ThinFilm` and a sample a
`CompositeSystem`. Their elements come from the chemical formulas of the
substrate and the targets, so NOMAD's search finds samples by element.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import timezone
from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import (
    CompositeSystem,
    CompositeSystemReference,
    SystemComponent,
)
from nomad.metainfo import MEnum, Quantity, Reference, Section, SubSection
from nomad.metainfo.metainfo import MetainfoReferenceError
from nomad_material_processing.general import CrystallineSubstrate, ThinFilm

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.composition import (
    apply_formula,
    chemical_formula_quantity,
    elements_of,
)
from differ_pld4e_schemas.database import (
    check_database_entry,
    check_database_reference,
)
from differ_pld4e_schemas.target import GENERATED, Target, in_stock_quantity
from differ_pld4e_schemas.time_zone import lab_wall_time

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'Layer',
    'Sample',
    'SampleInRun',
    'SampleRun',
    'SubstrateType',
    'assign_sample_numbers',
    'm_package',
    'made_here',
    'origin_or_default',
    'sample_id',
    'sample_name',
    'sample_uuid_for',
]

NEW_SAMPLE = 'New sample'
EXTERNAL_SAMPLE = 'External sample'
EXISTING_SAMPLE = 'Existing sample'
SAMPLE_ORIGINS = (NEW_SAMPLE, EXTERNAL_SAMPLE, EXISTING_SAMPLE)
MADE_HERE = (NEW_SAMPLE, EXTERNAL_SAMPLE)
# Sample UUIDs are derived from the sample ID in this namespace, so they are the
# same however often an entry is processed (see `sample_uuid_for`).
SAMPLE_UUID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    'https://github.com/timval-differ/differ-pld4energy-schemas/sample',
)
_SAMPLE_NUMBER = re.compile(r'_S(\d+)$')


def origin_or_default(origin):
    """A sample without an origin (none chosen yet) is a new sample."""
    return origin or NEW_SAMPLE


def made_here(origin) -> bool:
    """New and external samples are made (get their entry) in the run."""
    return origin_or_default(origin) in MADE_HERE


def sample_id(system, start, number):
    """
    `{system}_{yyyy-mm-dd}_{hh:mm}_S{nn}`, or None while a part is missing.
    `start` is on the lab's clock: the caller converts a stored datetime with
    `time_zone.lab_wall_time`.
    """
    if not system or start is None or not number:
        return None
    return f'{system}_{start:%Y-%m-%d_%H:%M}_S{int(number):02d}'


def number_of(sample_id_) -> int | None:
    """The nn of a sample ID ending in `_S{nn}`."""
    if not isinstance(sample_id_, str):
        return None
    match = _SAMPLE_NUMBER.search(sample_id_)
    return int(match.group(1)) if match else None


def assign_sample_numbers(rows) -> list:
    """
    The S-number of each sample of a run, from (made here, stored sample ID)
    pairs in list order: None for a sample not made here or one that keeps its
    stored ID; the others are numbered after the highest stored number. A
    number is never given twice, so a sample removed from the run does not
    pass its number (and its Sample entry) on to the next new one.
    """
    rows = list(rows)
    highest = max(
        (number_of(stored) or 0 for here, stored in rows if here and stored),
        default=0,
    )
    numbers = []
    for here, stored in rows:
        if here and not stored:
            highest += 1
            numbers.append(highest)
        else:
            numbers.append(None)
    return numbers


def sample_uuid_for(sample_id_) -> str | None:
    """The UUID of a sample, derived from its ID (e.g. for a QR code label)."""
    if not sample_id_:
        return None
    return str(uuid.uuid5(SAMPLE_UUID_NAMESPACE, sample_id_))


def _number_text(value) -> str:
    return f'{float(value):g}'


def sample_name(substrate_material, layers):
    """
    `Substrate_Film-<t>nm_Film-<n>p` from the substrate material and (material,
    thickness in nm[, number of pulses]) tuples. A film whose thickness is given
    as a number of pulses shows it as `<n>p`; layers without a material are
    left out.
    """
    if not substrate_material:
        return None
    parts = [substrate_material]
    for layer_material, thickness, *pulses in layers or []:
        if not layer_material:
            continue
        if thickness is not None:
            parts.append(f'{layer_material}-{_number_text(thickness)}nm')
        elif pulses and pulses[0] is not None:
            parts.append(f'{layer_material}-{_number_text(pulses[0])}p')
        else:
            parts.append(layer_material)
    return '_'.join(parts)


def file_name_for(text: str) -> str:
    return re.sub(r'[^\w.-]', '_', text) + '.archive.json'


def resolved(reference, *names):
    """Values of a referenced section, or Nones if it cannot be resolved."""
    if reference is None:
        return (None,) * len(names)
    try:
        return tuple(getattr(reference, name, None) for name in names)
    except MetainfoReferenceError:  # NOMAD reports the reference itself
        return (None,) * len(names)


def _resolvable(reference) -> bool:
    return resolved(reference, 'm_def') != (None,)


def _layer_pairs(layers):
    return [
        (
            layer.material,
            layer.thickness.to('nm').magnitude if layer.thickness is not None else None,
            layer.number_of_pulses,
        )
        for layer in layers or []
    ]


class SubstrateType(CrystallineSubstrate, EntryData):
    """
    A kind of substrate in the substrate database, e.g. SrTiO3 10x10 mm. Samples
    refer to it. Maintainers add an entry for every kind of substrate in use, in
    the target and substrate database upload.
    """

    m_def = Section(
        label='Substrate type',
        a_display={
            'visible': {'exclude': GENERATED},
            'order': [
                'name',
                'material',
                'chemical_formula',
                'size',
                'supplier',
                'supplier_id',
                'lab_id',
                'in_stock',
                'description',
            ],
        },
    )
    name = Quantity(
        type=str,
        description='Display name. Defaults to the material and size.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    material = Quantity(
        type=str,
        description='Substrate material as named in the lab, e.g. SrTiO3 or Si. '
        'Used in sample names.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    chemical_formula = chemical_formula_quantity()
    size = Quantity(
        type=str,
        description='e.g. 10x10 mm or 1" with flat.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    in_stock = in_stock_quantity()

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.name and self.material:
            self.name = ' '.join(part for part in (self.material, self.size) if part)
        check_database_entry(archive, logger, 'substrate type')
        apply_formula(self, archive, logger)
        super().normalize(archive, logger)


class Layer(ThinFilm):
    """
    A film grown on the sample, from one of the targets. Its elements are those
    of the target, so the sample (and the run) can be found by them.
    """

    m_def = Section(label_quantity='material')
    material = Quantity(
        type=str,
        description='Film material. Taken from the target if empty.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    thickness = Quantity(
        type=float,
        unit='m',
        description='Intended thickness of the film.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='nm'
        ),
    )
    number_of_pulses = Quantity(
        type=int,
        description='Intended thickness of the film as a number of laser pulses, '
        'when it is not given in nm.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    target = Quantity(
        type=Reference(Target.m_def),
        description='The target the film is grown from.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.material:
            (self.material,) = resolved(self.target, 'material')
        self.name = self.name or self.material
        if _resolvable(self.target):
            self.elemental_composition = elements_of(self.target)
        super().normalize(archive, logger)


class _SampleDetails(ArchiveSection):
    """What a sample and its entry in a run have in common."""

    m_def = Section()
    sample_id = Quantity(
        type=str,
        description='Generated as {system}_{yyyy-mm-dd}_{hh:mm}_S{nn}.',
    )
    sample_uuid = Quantity(
        type=str,
        description='Read-only: generated unique identifier, e.g. for a QR code label.',
    )
    origin = Quantity(
        type=MEnum(*SAMPLE_ORIGINS),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    substrate = Quantity(
        type=Reference(SubstrateType.m_def),
        description='The kind of substrate, from the substrate database.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    substrate_details = Quantity(
        type=str,
        description='Substrate of an external sample that is not in the database.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    substrate_material = Quantity(
        type=str,
        description='Read-only: taken from the substrate.',
    )
    substrate_size = Quantity(
        type=str,
        description='Read-only: taken from the substrate.',
    )
    substrate_batch_number = Quantity(
        type=str,
        description='Batch number of the substrate, as given by the supplier.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    layers = SubSection(section_def=Layer, repeats=True)

    def _copy_substrate_and_films(self) -> None:
        """Material and size from the substrate, film materials from the targets."""
        material, size = resolved(self.substrate, 'material', 'size')
        if material:
            self.substrate_material, self.substrate_size = material, size
        elif self.substrate is None and self.substrate_details:
            self.substrate_material = self.substrate_material or self.substrate_details
        for layer in self.layers or []:
            if not layer.material:
                (layer.material,) = resolved(layer.target, 'material')

    def _generated_name(self):
        return sample_name(self.substrate_material, _layer_pairs(self.layers))


class Sample(CompositeSystem, _SampleDetails, EntryData):
    """
    A sample: a substrate with the films grown on it. One entry per sample, so
    processes and measurements of any system can refer to it. Its elements are
    those of the substrate (a component) and of the films.
    """

    m_def = Section(
        label='Sample',
        label_quantity='sample_id',
        a_display={'visible': {'exclude': GENERATED}},
    )
    system = Quantity(
        type=str,
        description='The system the sample was made in, e.g. SA-PLD.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    made_in = Quantity(
        type=str,
        description='Read-only: the file of the logbook that made this entry. '
        'Only that logbook links it as a sample it made.',
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.sample_uuid:
            self.sample_uuid = sample_uuid_for(self.sample_id) or str(uuid.uuid4())
        check_database_reference(self.substrate, archive, logger, 'substrate')
        self._copy_substrate_and_films()
        if not self.name:
            self.name = self._generated_name()
        if self.sample_id and not self.lab_id:
            self.lab_id = self.sample_id
        self.components = (
            [SystemComponent(name=self.substrate_material, system=self.substrate)]
            if _resolvable(self.substrate)
            else []
        )
        super().normalize(archive, logger)
        if self.sample_id and archive is not None and archive.metadata is not None:
            archive.metadata.entry_name = self.sample_id


class SampleInRun(_SampleDetails, CompositeSystemReference):
    """
    A sample made or processed in a run. A new or external sample gets its own
    Sample entry on save, linked in `reference`; an existing sample is selected
    there. `layers` are the films grown in this run; the dashboard takes them
    from the deposition steps. An external sample may already carry films:
    those are `prior_layers`.
    """

    m_def = Section(label_quantity='sample_id')
    name = Quantity(
        type=str,
        description='Generated as Substrate_Film-thickness_Film-thickness.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    comments = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )
    reference = Quantity(
        type=Reference(Sample.m_def),
        description='The Sample entry of this sample.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ReferenceEditQuantity, label='Sample'
        ),
    )
    prior_layers = SubSection(
        section_def=Layer,
        repeats=True,
        description='Films already on an external sample, from the substrate up.',
    )

    def _generated_name(self):
        layers = [*(self.prior_layers or []), *(self.layers or [])]
        return sample_name(self.substrate_material, _layer_pairs(layers))

    def to_sample(self, system, start, made_in=None) -> Sample:
        sample = Sample(
            name=self.name,
            datetime=start,
            description=self.comments,
            system=system,
            made_in=made_in,
            sample_id=self.sample_id,
            sample_uuid=self.sample_uuid,
            origin=self.origin,
            substrate=self.substrate,
            substrate_details=self.substrate_details,
            substrate_material=self.substrate_material,
            substrate_size=self.substrate_size,
            substrate_batch_number=self.substrate_batch_number,
        )
        # The Sample entry has the whole stack: the films it came with first.
        for layer in [*(self.prior_layers or []), *(self.layers or [])]:
            sample.layers.append(
                Layer(
                    material=layer.material,
                    thickness=layer.thickness,
                    number_of_pulses=layer.number_of_pulses,
                    target=layer.target,
                )
            )
        return sample


class SampleRun(ArchiveSection):
    """
    A run that starts from the samples it makes or processes. Mixed into a
    native process, whose `samples` it specialises.
    """

    m_def = Section()
    samples = SubSection(section_def=SampleInRun, repeats=True)

    def _normalize_samples(
        self, archive: EntryArchive, logger: BoundLogger, system, start
    ) -> None:
        items = list(self.samples or [])
        numbers = assign_sample_numbers(
            (made_here(item.origin), item.sample_id) for item in items
        )
        seen = set()
        for item, number in zip(items, numbers):
            if not made_here(item.origin):
                self._copy_existing(item)
            else:
                check_database_reference(item.substrate, archive, logger, 'substrate')
                if not item.sample_id:
                    item.sample_id = self._new_sample_id(archive, system, start, number)
                item._copy_substrate_and_films()
                if not item.name:
                    item.name = item._generated_name()
            if item.sample_id is not None:
                if item.sample_id in seen:
                    logger.warning(f'Sample {item.sample_id} is listed twice.')
                seen.add(item.sample_id)
            if not made_here(item.origin):
                if item.reference is None:
                    logger.warning('Select the existing sample.')
            elif item.reference is None and item.sample_id:
                item.reference = self._create_sample_entry(
                    item, archive, system, start, logger
                )
            if made_here(item.origin):
                # The UUID of the Sample entry, which owns it; else one from the ID.
                (linked_uuid,) = resolved(item.reference, 'sample_uuid')
                item.sample_uuid = (
                    linked_uuid or item.sample_uuid or sample_uuid_for(item.sample_id)
                )
            # The sample ID, as on the Sample entry. Only set once the entry is
            # linked: without a link NOMAD would look the entry up by it.
            if item.reference is not None and item.sample_id:
                item.lab_id = item.sample_id

    @staticmethod
    def _new_sample_id(archive, system, start, number):
        """
        The ID of a new sample, from the run start on the lab's clock. Earlier
        versions used UTC: a sample whose entry was made with that ID keeps it.
        """
        if start is None:
            return None
        new = sample_id(system, lab_wall_time(start), number)
        utc = start.astimezone(timezone.utc) if start.tzinfo else start
        legacy = sample_id(system, utc, number)
        context = getattr(archive, 'm_context', None) if archive is not None else None
        if legacy != new and context is not None:
            try:
                if context.raw_path_exists(
                    file_name_for(legacy)
                ) and not context.raw_path_exists(file_name_for(new)):
                    return legacy
            except (NotImplementedError, OSError, TypeError):
                pass
        return new

    @staticmethod
    def _copy_existing(item: SampleInRun) -> None:
        """The ID, name and UUID of an existing sample come from its entry."""
        sample_id_, name, sample_uuid = resolved(
            item.reference, 'sample_id', 'name', 'sample_uuid'
        )
        item.sample_id = item.sample_id or sample_id_
        item.name = item.name or name
        if sample_uuid:
            item.sample_uuid = sample_uuid

    @staticmethod
    def _sample_file_owner(archive: EntryArchive, file_name: str):
        """(exists, the logbook that made it) of a Sample file in the upload."""
        context = archive.m_context
        if not context.raw_path_exists(file_name):
            return False, None
        try:
            with context.raw_file(file_name) as file:
                data = json.load(file).get('data') or {}
        except (OSError, ValueError, AttributeError):
            return True, None
        return True, data.get('made_in')

    @classmethod
    def _create_sample_entry(  # noqa: PLR0913
        cls, item: SampleInRun, archive: EntryArchive, system, start, logger
    ):
        """
        The Sample entry of a sample made in this run: written into the upload,
        or the one made by an earlier save of this logbook. A file of this
        sample ID made by another logbook is not linked: the two runs would
        share one sample.
        """
        if archive is None or archive.m_context is None or archive.metadata is None:
            return None
        if not archive.metadata.upload_id:
            return None
        from nomad.datamodel.context import ClientContext
        from nomad_material_processing.utils import create_archive

        if isinstance(archive.m_context, ClientContext):
            return None
        mainfile = archive.metadata.mainfile
        file_name = file_name_for(item.sample_id)
        exists, owner = cls._sample_file_owner(archive, file_name)
        if exists and owner and mainfile and owner != mainfile:
            logger.error(
                f'Sample {item.sample_id}: {file_name} was made by the logbook '
                f'{owner}, so it is not linked here. Check the start of the run, '
                'or enter the sample ID of this sample.'
            )
            return None
        if exists and not owner:
            logger.warning(
                f'Sample {item.sample_id}: linked to the existing {file_name}, '
                'which does not record the logbook that made it.'
            )
        return create_archive(
            item.to_sample(system, start, made_in=mainfile), archive, file_name
        )
