from django.contrib.auth.models import Group

class UserGroupSession: 
    def __init__(self, request):
        self.request = request

    def get_group_session(self):
         
         return Group.objects.get(pk=self.request.session['group_id'])

    def set_group_session(self):
        if 'group_id' not in self.request.session:
          
            groups =self.request.user.groups.all().order_by('id')

            if groups.exists():
                self.request.session['group_id'] = groups.first().id
             
