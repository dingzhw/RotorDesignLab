"""Resolve persisted solver semantics independently of widget revisions."""
AXIAL = '轴流性能（原均匀/环带模型）'
SPATIAL = '三方向来流（方位角叶素）'
MODELS = {AXIAL: 'aircraft_rotor', SPATIAL: 'spatial_rotor'}


def rotor_model(settings):
    explicit = settings.get('rotor', {}).get('flow_model')
    if explicit is not None:
        if explicit not in MODELS:
            raise ValueError('来流与旋翼模型：保存的模型名称无法识别，请明确选择。')
        return explicit
    # An actual saved calculation has stronger provenance than widget state.
    saved = settings.get('_last_rotor_case', {}).get('model')
    for label, model in MODELS.items():
        if saved == model:
            return label
    saved = settings.get('_effective_rotor_model')
    for label, model in MODELS.items():
        if saved == model:
            return label
    revision = settings.get('_workspace_revision')
    if revision is None:
        return AXIAL
    if revision in (4, 5, 6):
        return SPATIAL
    # Revision 3 was used both for new spatial designs and migrated axial ones.
    return None


def stamp(settings, version):
    choice = rotor_model(settings)
    settings['_producer_version'] = version
    settings['_effective_rotor_model'] = MODELS.get(choice)
    if choice is not None:
        settings.setdefault('rotor', {})['flow_model'] = choice
