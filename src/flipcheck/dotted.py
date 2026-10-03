import copy


def split_path(path: str) -> list[str]:
    return path.split(".") if path else []


def get_path(data, path: str):
    node = data
    for part in split_path(path):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise KeyError(path)
    return node


def path_exists(data, path: str) -> bool:
    try:
        get_path(data, path)
        return True
    except KeyError:
        return False


def _parent_and_key(data: dict, path: str) -> tuple[dict, str]:
    parts = split_path(path)
    node = data
    for part in parts[:-1]:
        node = node[part]
    return node, parts[-1]


def remove_path(data: dict, path: str) -> dict:
    result = copy.deepcopy(data)
    node, key = _parent_and_key(result, path)
    del node[key]
    return result


def append_text(data: dict, path: str, text: str) -> dict:
    result = copy.deepcopy(data)
    node, key = _parent_and_key(result, path)
    node[key] = f"{node[key]}\n{text}"
    return result


def inject_by_type(data: dict, path: str, text: str) -> dict:
    # inject by field type: string appends, object gets a "note" key, array gets an element
    value = get_path(data, path)
    if isinstance(value, dict):
        result = copy.deepcopy(data)
        node, key = _parent_and_key(result, path)
        node[key] = {**node[key], "note": text}
        return result
    if isinstance(value, list):
        result = copy.deepcopy(data)
        node, key = _parent_and_key(result, path)
        node[key] = [*node[key], text]
        return result
    return append_text(data, path, text)
