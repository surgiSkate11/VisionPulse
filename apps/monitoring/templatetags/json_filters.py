import json
from django import template

register = template.Library()

@register.filter
def jsonify(obj):
    """
    Convierte un objeto Python a string JSON seguro para usar en templates
    """
    return json.dumps(obj)