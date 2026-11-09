# SPDX-License-Identifier: GPL-3.0-only
from ruamel.yaml import YAML

def validate_max_data(blob):
    data = YAML(typ='safe').load(blob.decode('utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('invalid resource table')
    for key in ('character', 'skin', 'title', 'item', 'loading_image', 'endings'):
        values = data.get(key)
        if not isinstance(values, list) or not values or any(type(v) is not int or v <= 0 for v in values):
            raise ValueError('invalid resource table: ' + key)
    if not isinstance(data.get('emoji'), dict):
        raise ValueError('missing emoji table')
    return data
