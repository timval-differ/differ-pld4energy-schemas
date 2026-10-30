"""
The samples a run starts from: form section, computed IDs and names, and the
conversion to and from archive files. Independent of the system, so any run
dashboard can use it; it only expects the run's system, date and time under
`/run/system`, `/run/date` and `/run/time`. The films of a sample are not part
of this section: the dashboard derives them from its process steps and passes
them in as {'target', 'material', 'thickness' (nm)}.

Form data of one sample::

    {
        'uid': ..., 'origin': 'New sample',
        'substrate': ...,           # reference to a Substrate type entry
        'substrate_material': ...,  # copied from it by the browser
        'substrate_details': ...,
        'comments': ...,
        'sample': ...,       # reference, for an existing sample
        'ref': ...,          # reference to the Sample entry made for this sample
        'sample_id': ...,    # stored once the Sample entry exists
        'sample_uuid': ...,
    }
"""

from __future__ import annotations

import uuid
from datetime import datetime

from differ_pld4e_schemas.sample import (
    EXISTING_SAMPLE,
    EXTERNAL_SAMPLE,
    NEW_SAMPLE,
    SAMPLE_ORIGINS,
    Layer,
    Sample,
    SampleInRun,
    sample_id,
    sample_name,
)

from .archive import (
    file_name_for,
    fill,
    is_mainfile_reference,
    mainfile_reference,
    normalize_reference,
    quantity_of,
    read,
    to_archive_value,
)
from .fields import comments, field, number
from .values import lookup, parse_date, parse_time, to_number

MADE_HERE = (NEW_SAMPLE, EXTERNAL_SAMPLE)


def origin_is(*origins) -> dict:
    return {'key': 'origin', 'in': list(origins)}


# Values the browser copies from a chosen entry, as {form key: entry field}.
SUBSTRATE_COPY = {'substrate_material': 'material'}
THICKNESS = number('thickness', 'Thickness', 'nm')


def sample_section() -> dict:
    """The form section listing the samples of a run."""
    return {
        'key': 'samples',
        'title': 'Samples',
        'kind': 'list',
        'item_label': 'Sample',
        'min_items': 1,
        'count_control': True,
        'intro': (
            'List the samples you make or process in this run. A sample is a '
            'substrate with the films grown on it. New and external samples get '
            'a sample ID from the system, date and time of the run.'
        ),
        'unique': ['sample_id', 'sample'],
        'fields': [
            field(
                'origin',
                'Sample',
                'select',
                options=list(SAMPLE_ORIGINS),
                default=NEW_SAMPLE,
            ),
            field(
                'sample',
                'Existing sample',
                'reference',
                reference='sample',
                archive=None,
                visible_if=origin_is(EXISTING_SAMPLE),
            ),
            field(
                'substrate',
                'Substrate',
                'reference',
                reference='substrate',
                ref_copy=SUBSTRATE_COPY,
                # Written by the converter, with what is copied from the entry.
                archive=None,
                visible_if=origin_is(*MADE_HERE),
                # An external sample may be on a substrate not in the database.
                required_if=origin_is(NEW_SAMPLE),
            ),
            field(
                'substrate_details',
                'Substrate details',
                placeholder='e.g. MgO (001) 5x5 mm',
                visible_if={
                    'all': [
                        origin_is(EXTERNAL_SAMPLE),
                        {'key': 'substrate', 'equals': False},
                    ]
                },
            ),
            field(
                'prior_films',
                'Films already on the sample',
                'rows',
                item_label='film',
                archive='prior_layers',
                visible_if=origin_is(EXTERNAL_SAMPLE),
                help='From the substrate up. The films grown in this run come from '
                'the deposition steps.',
                columns=[
                    field('material', 'Material', placeholder='e.g. SrRuO3'),
                    number('thickness', 'Thickness', 'nm', required=False),
                ],
            ),
            field(
                'sample_id',
                'Sample ID',
                'computed',
                compute='sample_id',
                archive=None,
            ),
            field(
                'name',
                'Sample name',
                'computed',
                compute='sample_name',
                archive=None,
            ),
            comments(archive='comments'),
        ],
    }


def run_start(root: dict) -> datetime | None:
    """Local start of the run from `/run/date` and `/run/time`."""
    day = parse_date(lookup('/run/date', {}, root))
    clock = parse_time(lookup('/run/time', {}, root))
    if day is None or clock is None:
        return None
    return datetime.combine(day, clock)


def sample_number(item: dict, root: dict) -> int | None:
    """Position of a new or external sample among those of the run (from 1)."""
    number = 0
    for other in root.get('samples') or []:
        if other.get('origin', NEW_SAMPLE) not in MADE_HERE:
            continue
        number += 1
        if other is item or (item.get('uid') and other.get('uid') == item['uid']):
            return number
    return None


def compute_sample_id(item: dict, root: dict):
    # An existing sample keeps its ID, and so does a sample whose entry exists.
    if item.get('origin', NEW_SAMPLE) not in MADE_HERE or item.get('ref'):
        return item.get('sample_id')
    return sample_id(
        lookup('/run/system', item, root), run_start(root), sample_number(item, root)
    )


def prior_films(item: dict) -> list:
    """Films an external sample already has when it comes into the run."""
    if item.get('origin') != EXTERNAL_SAMPLE:
        return []
    return list(item.get('prior_films') or [])


def compute_sample_name(item: dict, root: dict, films: list):
    """From the substrate, the films it came with and those grown in this run."""
    if item.get('origin', NEW_SAMPLE) not in MADE_HERE:
        return item.get('name')
    layers = [
        (film.get('material'), to_number(film.get('thickness')))
        for film in [*prior_films(item), *films]
    ]
    return sample_name(_substrate_material(item), layers)


def _substrate_material(item: dict):
    if item.get('substrate'):
        return item.get('substrate_material')
    if item.get('origin') == EXTERNAL_SAMPLE:
        return item.get('substrate_details')
    return None


def sample_choices(root: dict) -> list:
    """Values a step can use to name one sample of the run."""
    choices = []
    for item in root.get('samples') or []:
        if item.get('origin', NEW_SAMPLE) in MADE_HERE:
            choices.append(f'new:{item.get("uid")}')
        elif item.get('sample'):
            choices.append(item['sample'])
    return choices


def _file_name(reference: str) -> str:
    return reference.split('/mainfile/', 1)[1].split('#', 1)[0]


def _sample_file(entry: dict, item: dict, system: str, start_text: str) -> dict:
    data = {
        'm_def': Sample.m_def.qualified_name(),
        'datetime': start_text,
        'system': system,
    }
    for key in (
        'name',
        'sample_id',
        'sample_uuid',
        'origin',
        'substrate',
        'substrate_details',
        'substrate_material',
    ):
        if entry.get(key) is not None:
            data[key] = entry[key]
    # The Sample entry has the whole stack: the films it came with first.
    layers = [*entry.get('prior_layers', []), *entry.get('layers', [])]
    if layers:
        data['layers'] = layers
    if entry.get('comments'):
        data['description'] = entry['comments']
    # The entry of a sample is made by its first save; later saves of the run
    # update it, but never touch samples of other runs.
    reference = item.get('ref')
    if reference and is_mainfile_reference(reference):
        file_name, overwrite = _file_name(reference), True
    else:
        file_name, overwrite = file_name_for(entry['sample_id']), False
        reference = mainfile_reference(file_name)
    return {
        'file_name': file_name,
        'kind': 'sample',
        'uid': item.get('uid'),
        'reference': reference,
        'overwrite': overwrite,
        'archive': {'data': data},
    }


def _layers_to_archive(films: list) -> list:
    layers = []
    for film in films:
        layer = {
            key: film[key]
            for key in ('target', 'material')
            if film.get(key) not in (None, '')
        }
        if to_number(film.get('thickness')) is not None:
            layer['thickness'] = to_archive_value(
                film['thickness'], THICKNESS, quantity_of(Layer, 'thickness')
            )
        if layer:
            layers.append(layer)
    return layers


def _substrate_to_archive(item: dict, entry: dict) -> None:
    if item.get('origin', NEW_SAMPLE) not in MADE_HERE:
        return
    if item.get('substrate'):
        entry['substrate'] = item['substrate']
    material = _substrate_material(item)
    if material:
        entry['substrate_material'] = material


def samples_to_archive(
    data: dict, fields: list, system: str, start_text: str, films_of
):
    """
    The `samples` of the run's archive, the Sample files to write and a map
    from the form's sample choices to references. `films_of(item)` gives the
    films grown on a sample in this run.
    """
    samples, files, references = [], [], {}
    for item in data.get('samples') or []:
        entry = {'sample_uuid': item.get('sample_uuid') or str(uuid.uuid4())}
        fill(entry, SampleInRun, fields, item, data)
        _substrate_to_archive(item, entry)
        films = films_of(item)
        layers = _layers_to_archive(films)
        if layers:
            entry['layers'] = layers
        for key, value in (
            ('sample_id', compute_sample_id(item, data)),
            ('name', compute_sample_name(item, data, films)),
        ):
            if value:
                entry[key] = value
        if entry.get('origin', NEW_SAMPLE) in MADE_HERE:
            reference = item.get('ref')
            if entry.get('sample_id') and (
                not reference or is_mainfile_reference(reference)
            ):
                file = _sample_file(entry, item, system, start_text)
                files.append(file)
                reference = file['reference']
            choice = f'new:{item.get("uid")}'
        else:
            reference = choice = item.get('sample')
        if reference:
            entry['sample'] = reference
            references[choice] = reference
        samples.append(entry)
    return samples, files, references


def samples_to_form(data: dict, fields: list, new_uid):
    """Form samples from an archive, and a map from references to choices."""
    samples, by_reference = [], {}
    for entry in data.get('samples') or []:
        item = read(entry, SampleInRun, fields)
        item.update(
            uid=new_uid(),
            sample_uuid=entry.get('sample_uuid'),
            sample_id=entry.get('sample_id'),
            name=entry.get('name'),
        )
        if entry.get('substrate'):
            item['substrate'] = normalize_reference(entry['substrate'])
            item['substrate_material'] = entry.get('substrate_material')
        item.setdefault('origin', NEW_SAMPLE)
        reference = normalize_reference(entry.get('sample'))
        if item['origin'] in MADE_HERE:
            item['ref'] = entry.get('sample')
            choice = f'new:{item["uid"]}'
        else:
            item['sample'] = reference
            choice = reference
        if reference:
            by_reference[reference] = choice
        samples.append(item)
    return samples, by_reference
