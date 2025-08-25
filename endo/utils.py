import math

def clean_json(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return ""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_json(x) for x in obj]
    return obj


