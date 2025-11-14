"""
Context processors para VisionPulse
Agregan variables globales disponibles en todos los templates
"""

def user_groups(request):
    """
    Agrega información sobre los grupos del usuario al contexto
    """
    context = {
        'is_empresa_user': False,
    }
    
    if request.user.is_authenticated:
        # Soporta coincidencia por nombre independientemente de mayúsculas/minúsculas
        context['is_empresa_user'] = request.user.groups.filter(name__iexact='empresa').exists()
    
    return context
