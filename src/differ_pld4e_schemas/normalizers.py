from differ_pld4e_schemas.thin_film import ThinFilm, ThinFilmStack


def normalize_deposition(deposition, archive, logger):
    """Validate deposition values and assemble the resulting stack."""
    for step in deposition.steps or []:
        if step.deposition_time is not None and step.deposition_time <= 0:
            logger.error('Deposition time must be greater than 0.')

        layer = step.deposited_layer
        if layer is not None and layer.thickness is not None and layer.thickness < 0:
            logger.error('Film thickness cannot be negative.')

        environment = step.chamber_environment
        if (
            environment is not None
            and environment.working_pressure is not None
            and environment.base_pressure is not None
            and environment.working_pressure < environment.base_pressure
        ):
            logger.warning(
                'Working pressure is lower than base pressure. Please check logs.'
            )

        source = step.source
        target = source.target if source is not None else None
        if (
            target is not None
            and layer is not None
            and target.material
            and layer.material
            and target.material != layer.material
            and step.sputtering_technique != 'Reactive'
        ):
            logger.warning(
                f'Target material ({target.material}) differs from film material '
                f'({layer.material}) and technique is not Reactive.'
            )

    if deposition.substrate is None or not deposition.steps:
        return

    layers = []
    total_thickness = 0.0
    for step_index, step in enumerate(deposition.steps):
        layer = step.deposited_layer
        if layer is None:
            continue
        layer_data = {
            name: getattr(layer, name)
            for name in (
                'layer_name',
                'material',
                'thickness',
                'deposition_rate',
                'composition',
                'source_target',
                'deposition_step_reference',
            )
            if getattr(layer, name) is not None
        }
        if layer_data.get('source_target') is None and step.source is not None:
            layer_data['source_target'] = step.source.target
        if not layer_data.get('deposition_step_reference'):
            layer_data['deposition_step_reference'] = (
                step.name or f'step-{step_index + 1}'
            )
        layers.append(ThinFilm(**layer_data))
        if layer.thickness is not None:
            total_thickness += layer.thickness

    stack = deposition.resulting_stack
    if stack is None:
        stack = ThinFilmStack()
        deposition.resulting_stack = stack
    stack.stack_name = stack.stack_name or (
        f'Stack on {deposition.substrate.sample_id or "Substrate"}'
    )
    stack.substrate = deposition.substrate
    stack.layers = layers
    stack.total_thickness = total_thickness
