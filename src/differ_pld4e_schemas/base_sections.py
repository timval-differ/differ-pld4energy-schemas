"""
What the logbooks add to the native NOMAD process (`PulsedLaserDeposition`,
`SputterDeposition`): the operator of the run, and a name when none is given.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Section

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.time_zone import lab_wall_time

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

NO_START = (
    'The start of the run (datetime) is not given, so the time the entry was '
    'created is used. Enter it: the sample IDs are made from it.'
)
NO_START_AT_ALL = (
    'Enter the start of the run (datetime): without it the samples get no '
    'sample IDs and no Sample entries.'
)

__all__ = ['RunDetails', 'm_package']


class RunDetails(ArchiveSection):
    """Who carried out a run. Mixed into a native process."""

    m_def = Section()
    operator_name = Quantity(
        type=str,
        description='The person who carried out the process.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    operator_email = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )

    def default_datetime(self, archive: EntryArchive, logger: BoundLogger) -> None:
        """
        A run without a start gets the time its entry was created, which stays
        the same when the entry is processed again (the time of processing
        would give new sample IDs, and new Sample entries, each time).
        """
        if self.datetime is not None:
            return
        metadata = archive.metadata if archive is not None else None
        created = metadata.entry_create_time if metadata is not None else None
        if created is not None:
            self.datetime = created
            logger.warning(NO_START)
        else:
            logger.error(NO_START_AT_ALL)

    def default_name(self, system: str) -> None:
        """
        `<system> <yyyy-mm-dd hh:mm>` (on the lab's clock) for a run without a
        name; it also names the entry. (NOMAD would otherwise take the entry
        name, which may not be set yet.)
        """
        if self.name:
            return
        if self.datetime is not None:
            self.name = f'{system} {lab_wall_time(self.datetime):%Y-%m-%d %H:%M}'
        else:
            self.name = f'{system} run'
