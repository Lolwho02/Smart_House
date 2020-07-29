from django.urls import reverse_lazy
from django.views.generic import FormView

from .models import Setting
from .form import ControllerForm
from .tasks import Processor

class ControllerView(FormView):
    
    form_class = ControllerForm
    template_name = 'core/control.html'
    success_url = reverse_lazy('form')

    def get_context_data(self, **kwargs):
        """Returns a dictionary representing the template context. 
        The keyword arguments provided will make up the returned context. """
       
        context = super(ControllerView, self).get_context_data()
        context['data'] = Processor.storage
        return context

    def get_initial(self):  # для получения начальных данных формы
        return {
        'bedroom_light':Processor.storage['bedroom_light'],
        'bathroom_light':Processor.storage['bathroom_light'],
        'bedroom_target_temperature':Processor.storage['bedroom_target_temperature'],
        'hot_water_target_temperature':Processor.storage['hot_water_target_temperature']
        }

    def form_valid(self, form):
        Processor.storage['bedroom_light'] = Processor.control_bedroom_light(form.cleaned_data['bedroom_light'])
        Processor.storage['bathroom_light'] = Processor.control_bathroom_light(form.cleaned_data['bathroom_light'])
        Processor.storage['bedroom_target_temperature'] = Processor.control_bedroom_target_temperature(form.cleaned_data['bedroom_target_temperature'])
        Processor.storage['hot_water_target_temperature'] = Processor.control_hot_water_target_temperature(form.cleaned_data['hot_water_target_temperature'])
        return super(ControllerView, self).form_valid(form)  # по умолчанию производит редирект на URL success_url