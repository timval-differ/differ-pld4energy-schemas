from typing import Optional

from nomad.config.models.plugins import SchemaPackageEntryPoint
from pydantic import Field, field_validator


class PLD4ESchemasEntryPoint(SchemaPackageEntryPoint):
    database_upload_id: Optional[str] = Field(  # noqa: UP045 (Python 3.9)
        None,
        description=(
            'The upload that holds the target and substrate database. Make the '
            'maintainers its coauthors and everyone else a reviewer: logbooks '
            'and samples only choose targets and substrates from this upload.'
        ),
    )
    lab_time_zone: str = Field(
        'Europe/Amsterdam',
        description=(
            'The IANA time zone of the lab, e.g. Europe/Amsterdam. Run and step '
            'times are entered on the lab clock and shown on it again, and the '
            'sample IDs use it, wherever the logbook is opened.'
        ),
    )

    @field_validator('lab_time_zone')
    @classmethod
    def _known_time_zone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f'Unknown time zone {value!r}.') from error
        return value

    def load(self):
        from differ_pld4e_schemas.schema_packages.schema_package import m_package

        return m_package


schema_package_entry_point = PLD4ESchemasEntryPoint(
    name='PLD4Energy Schemas',
    description='Schemas for the SA-PLD, LA-PLD and SPS logbooks, their samples, '
    'targets and substrates, and the in-situ techniques.',
)
