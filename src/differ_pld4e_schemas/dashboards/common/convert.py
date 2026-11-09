"""
Conversion between a logbook form and NOMAD archive files, for the parts every
logbook has: run, samples, system details, targets and process steps. A
dashboard subclasses `LogbookConverter` for sections of its own (e.g. the
laser of the PLD logbook).

Values are entered in lab units (mbar, mJ, °C, ...) and stored in the units of
the schema quantities (SI), using the `unit` of each form field.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from differ_pld4e_schemas.gas import BACKGROUND_GAS, GASES, BackgroundGas
from differ_pld4e_schemas.time_zone import lab_instant, lab_wall_time

from .archive import (
    file_name_for,
    fill,
    normalize_reference,
    quantity_of,
    read,
    to_archive_value,
    to_form_value,
)
from .rules import section_requirement
from .samples import samples_to_archive, samples_to_form
from .values import (
    is_empty,
    parse_date,
    parse_time,
    step_times,
    to_number,
    visible_fields,
)

DRAFT_SUFFIX = '.draft.json'


class UnsafeLogbookFile(ValueError):
    """The logbook file a save would overwrite is not one this dashboard makes."""


class NotALogbook(ValueError):
    """The archive read into the form is not a logbook of this dashboard."""


def is_logbook_file(name, systems) -> bool:
    """
    Whether `name` is a logbook file name as made by `run_file_stem`:
    `{system}_{yyyy-mm-dd}_{hhmm}[_{name}].archive.json`. Sample files
    (`..._{hh}_{mm}_S{nn}`) and hand-made `.archive.yaml` logbooks do not match.
    """
    if not isinstance(name, str) or not systems:
        return False
    alternatives = '|'.join(re.escape(system) for system in systems)
    return bool(
        re.fullmatch(
            rf'(?:{alternatives})_\d{{4}}-\d{{2}}-\d{{2}}_\d{{4}}(?:_[\w.-]+)?'
            r'\.archive\.json',
            name,
        )
    )


def run_file_stem(data: dict) -> str:
    """`{system}_{date}_{hhmm}[_{name}]`, the start of the run's file names."""
    run = data.get('run') or {}
    stem = f'{run["system"]}_{run["date"]}_{run["time"].replace(":", "")}'
    if run.get('name'):
        stem += f'_{run["name"]}'
    return re.sub(r'[^\w.-]', '_', stem)


def sections_of(spec: dict) -> dict:
    return {section['key']: section for section in spec['sections']}


def run_datetime(run: dict) -> str:
    """The start of the run, its date and time on the lab's clock. A browser's
    `utc_offset` (sent by older pages and drafts) is ignored."""
    return lab_instant(parse_date(run['date']), parse_time(run['time'])).isoformat()


def parse_datetime(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def step_clock_times(step: dict) -> dict:
    """The hh:mm start and end of an archived step, on the lab's clock."""
    form = {}
    for key in ('start_time', 'end_time'):
        moment = parse_datetime(step.get(key)) if step.get(key) else None
        if moment is None:
            continue
        form[key] = lab_wall_time(moment).strftime('%H:%M')
    return form


def seconds_between(start: datetime, end: datetime) -> float:
    """Real elapsed time: datetimes of one time zone subtract as wall-clock
    times, which is an hour off over a clock change."""
    return (
        end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    ).total_seconds()


def new_uid() -> str:
    return uuid.uuid4().hex[:12]


def gases_to_archive(fields, item, root) -> list:
    if item.get('atmosphere', BACKGROUND_GAS) != BACKGROUND_GAS:
        return []
    visible = visible_fields(fields, item, root)
    shown = {f['key'] for f in visible}
    gases = []
    for gas in GASES:
        if f'gas_{gas}' not in shown or not item.get(f'gas_{gas}'):
            continue
        entry = {'gas': gas}
        for field in visible:
            if field.get('gas') != gas or field['archive'] is None:
                continue
            value = item.get(field['key'])
            if is_empty(value):
                continue
            quantity = quantity_of(BackgroundGas, field['archive'])
            entry[field['archive']] = to_archive_value(value, field, quantity)
        gases.append(entry)
    return gases


def gases_to_form(fields, gases) -> dict:
    form = {}
    for entry in gases or []:
        gas = entry.get('gas')
        if gas not in GASES:
            continue
        form[f'gas_{gas}'] = True
        for field in fields:
            if field.get('gas') != gas or field['archive'] is None:
                continue
            if entry.get(field['archive']) is not None:
                quantity = quantity_of(BackgroundGas, field['archive'])
                form[field['key']] = to_form_value(
                    entry[field['archive']], field, quantity
                )
    return form


def targets_to_archive(data: dict) -> list:
    targets = []
    for item in data.get('targets') or []:
        if not item.get('target') or to_number(item.get('target_number')) is None:
            continue
        target = {
            'target_number': int(to_number(item['target_number'])),
            'target': item['target'],
        }
        # Also copied from the target entry on save; it names the films.
        if item.get('material'):
            target['material'] = item['material']
        targets.append(target)
    return targets


def targets_to_form(data: dict) -> list:
    return [
        {
            'uid': new_uid(),
            'target': normalize_reference(item.get('target')),
            'material': item.get('material'),
            # A choice in the form, so the number as text.
            'target_number': (
                str(item['target_number'])
                if item.get('target_number') is not None
                else None
            ),
        }
        for item in data.get('targets') or []
    ]


class LogbookConverter:
    """
    Form ⇄ archive of one logbook dashboard.

    logbook_sections   {system: logbook section class}
    step_module        module holding the step classes named by the variants
    rules              the dashboard's `LogbookRules`
    draft_dir          directory of the drafts in the upload
    """

    def __init__(self, logbook_sections: dict, step_module, rules, draft_dir: str):
        self.logbook_sections = logbook_sections
        self.step_module = step_module
        self.rules = rules
        self.draft_dir = draft_dir

    # Hooks for the sections of one dashboard.

    def extra_to_archive(
        self, data: dict, spec: dict, logbook: dict, references: dict
    ) -> None:
        """
        Write the dashboard's own sections into the logbook archive.
        `references` maps the form's sample choices to Sample references.
        """

    def extra_to_form(
        self, data: dict, spec: dict, form: dict, by_reference: dict
    ) -> None:
        """
        Read the dashboard's own sections from the logbook archive.
        `by_reference` maps Sample references to the form's sample choices.
        """

    # Files and drafts.

    def draft_path(self, data: dict) -> str:
        return f'{self.draft_dir}/{run_file_stem(data)}{DRAFT_SUFFIX}'

    def step_class(self, variant: dict, system: str):
        return getattr(self.step_module, variant['sections'][system])

    def step_samples(self, item: dict, system: str, references: dict) -> list:
        if system in self.rules.all_samples:
            return list(references.values())
        chosen = item.get('sample')
        return [references.get(chosen, chosen)] if chosen else []

    def steps_to_archive(self, data: dict, spec: dict, system: str, references):
        steps = []
        variants = sections_of(spec)['steps']['variants']
        items = data.get('steps') or []
        times = step_times(data.get('run') or {}, items)
        for item, (start, end) in zip(items, times):
            variant = variants[item['type']]
            step_cls = self.step_class(variant, system)
            step = {'m_def': step_cls.m_def.qualified_name()}
            fill(step, step_cls, variant['fields'], item, data)
            if start:
                step['start_time'] = start.isoformat()
            if end:
                step['end_time'] = end.isoformat()
            if start and end:
                step['duration'] = seconds_between(start, end)
            if 'samples' in step_cls.m_def.all_quantities:
                samples = self.step_samples(item, system, references)
                if samples:
                    step['samples'] = samples
            step['background_gases'] = gases_to_archive(variant['fields'], item, data)
            steps.append(step)
        return steps

    def form_to_files(
        self, data: dict, spec: dict, logbook_file: str | None = None
    ) -> dict:
        """
        The archive files for a complete (validated) form: one Sample file per
        new or external sample, then the logbook. References between them use
        file names, so everything can be written in one go.

        `logbook_file` is the file of an opened logbook, which the save
        overwrites. It comes from the browser, so it must be a logbook file name
        this dashboard makes (`is_logbook_file`), else `UnsafeLogbookFile`.
        """
        if logbook_file is not None and not is_logbook_file(
            logbook_file, spec.get('systems')
        ):
            raise UnsafeLogbookFile(
                f'{logbook_file} is not a logbook made by this dashboard, so it '
                'cannot be overwritten. Save the logbook as a new file instead.'
            )
        sections = sections_of(spec)
        run = data.get('run') or {}
        system = run['system']
        logbook_cls = self.logbook_sections[system]
        start = run_datetime(run)

        logbook = {'m_def': logbook_cls.m_def.qualified_name()}
        fill(logbook, logbook_cls, sections['run']['fields'], run, data)
        fill(
            logbook,
            logbook_cls,
            sections['chamber']['fields'],
            data.get('chamber') or {},
            data,
        )
        logbook['datetime'] = start
        # The schema only has it as a default, which NOMAD does not show as a value.
        logbook['pvd_system'] = system
        # Only an opened logbook (with its file name given) may be overwritten.
        overwrite = logbook_file is not None
        if logbook_file is None:
            logbook_file = file_name_for(run_file_stem(data))
        logbook['samples'], files, references, warnings = samples_to_archive(
            data,
            sections['samples']['fields'],
            start,
            lambda item: self.rules.sample_films(item, data),
            spec.get('systems'),
            made_in=logbook_file,
        )
        if section_requirement(sections['targets'], spec, data) != 'none':
            targets = targets_to_archive(data)
            if targets:
                logbook['targets'] = targets
        logbook['steps'] = self.steps_to_archive(data, spec, system, references)
        self.extra_to_archive(data, spec, logbook, references)
        if data.get('recipe') and 'load_recipe' in logbook_cls.m_def.all_sub_sections:
            logbook['load_recipe'] = {'recipe': data['recipe']}

        files.append(
            {
                'file_name': logbook_file,
                'kind': 'logbook',
                'overwrite': overwrite,
                'archive': {'data': logbook},
            }
        )
        return {'files': files, 'logbook_file': logbook_file, 'warnings': warnings}

    # Reading an archive back into the form.

    def system_of(self, data: dict) -> str | None:
        m_def = data.get('m_def') or ''
        for system, section in self.logbook_sections.items():
            if m_def == section.m_def.qualified_name() or m_def.endswith(
                f'.{section.__name__}'
            ):
                return system
        return None

    @staticmethod
    def variant_of(variants: dict, m_def: str, system: str):
        for key, variant in variants.items():
            if (m_def or '').endswith(f'.{variant["sections"][system]}'):
                return key
        return None

    def steps_to_form(self, data, spec, system, samples, by_reference) -> list:
        """
        Form steps; samples used by steps but not in the logbook are added.
        Each step keeps its position in the archive as `archive_index` (removed
        again by `archive_to_form`), so references to it can be resolved.
        """
        steps = []
        variants = sections_of(spec)['steps']['variants']
        for index, item in enumerate(data.get('steps') or []):
            variant_key = self.variant_of(variants, item.get('m_def'), system)
            if variant_key is None:
                continue
            variant = variants[variant_key]
            form_item = read(item, self.step_class(variant, system), variant['fields'])
            form_item.update(
                gases_to_form(variant['fields'], item.get('background_gases'))
            )
            form_item.update(step_clock_times(item))
            form_item.update(uid=new_uid(), type=variant_key, archive_index=index)
            step_samples = item.get('samples') or []
            if system not in self.rules.all_samples and step_samples:
                reference = normalize_reference(step_samples[0])
                if reference not in by_reference:
                    samples.append(
                        {
                            'uid': new_uid(),
                            'origin': 'Existing sample',
                            'sample': reference,
                        }
                    )
                    by_reference[reference] = reference
                form_item['sample'] = by_reference[reference]
            steps.append(form_item)
        return steps

    def run_to_form(self, data: dict, run_fields: list, system: str) -> dict:
        run = read(data, self.logbook_sections[system], run_fields)
        run['system'] = system
        start = parse_datetime(data.get('datetime')) if data.get('datetime') else None
        if start is not None:
            # NOMAD gives the start back in UTC; the form is on the lab's clock.
            start = lab_wall_time(start)
            run['date'], run['time'] = (
                start.strftime('%Y-%m-%d'),
                start.strftime('%H:%M'),
            )
        return run

    def archive_to_form(self, data: dict, spec: dict) -> dict:
        """
        Form data from the `data` section of a logbook archive, e.g. to edit a
        saved logbook or to take the steps of a recipe.
        """
        system = self.system_of(data)
        if system is None:
            raise NotALogbook(
                f'This entry is not a logbook of {" or ".join(self.logbook_sections)}.'
            )
        sections = sections_of(spec)
        samples, by_reference = samples_to_form(
            data, sections['samples']['fields'], new_uid
        )
        steps = self.steps_to_form(data, spec, system, samples, by_reference)
        form = {
            'run': self.run_to_form(data, sections['run']['fields'], system),
            'samples': samples,
            'chamber': read(
                data, self.logbook_sections[system], sections['chamber']['fields']
            ),
            'targets': targets_to_form(data),
            'steps': steps,
        }
        self.extra_to_form(data, spec, form, by_reference)
        for step in steps:
            del step['archive_index']
        recipe = (data.get('load_recipe') or {}).get('recipe')
        if recipe:
            form['recipe'] = recipe
        return form

    def recipe_to_form(self, data: dict, spec: dict) -> dict:
        """The steps (and targets) of a recipe, without sample links."""
        form = self.archive_to_form(data, spec)
        for step in form['steps']:
            step.pop('sample', None)
            # A recipe is run again at another time.
            step.pop('start_time', None)
            step.pop('end_time', None)
        return {
            'system': form['run']['system'],
            'targets': form['targets'],
            'steps': form['steps'],
        }
