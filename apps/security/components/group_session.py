from django.contrib.auth.models import Group

class UserGroupSession: 
    def __init__(self, request):
        self.request = request

    def get_group_session(self):
        # Si el usuario es superusuario, no requiere grupo
        if self.request.user.is_superuser:
            return None
        # Si no hay 'group_id' en la sesión, lo asigna automáticamente
        if 'group_id' not in self.request.session:
            groups = self.request.user.groups.all().order_by('id')
            if groups.exists():
                self.request.session['group_id'] = groups.first().id
            else:
                # Si el usuario no tiene grupos, retorna None
                return None
        return Group.objects.get(pk=self.request.session['group_id'])

    def set_group_session(self):
        if 'group_id' not in self.request.session:
          
            groups =self.request.user.groups.all().order_by('id')

            if groups.exists():
                self.request.session['group_id'] = groups.first().id

