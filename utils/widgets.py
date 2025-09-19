from django import forms
import json

class ColorPickerWidget(forms.TextInput):
    """
    Widget para seleccionar colores con picker visual
    """
    input_type = 'color'
    
    def __init__(self, attrs=None):
        default_attrs = {'class': 'form-control color-picker'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    class Media:
        css = {
            'all': ('forms/color_picker.css',)
        }
        js = ('forms/color_picker.js',)

class EmojiPickerWidget(forms.TextInput):
    """
    Widget para seleccionar emojis con selector visual
    """
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control emoji-picker',
            'maxlength': '2',
            'placeholder': '📚'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        
        # Lista de emojis comunes para cursos
        emojis = [
            '📚', '📖', '✏️', '🎓', '🧮', '🔬', '🎨', '🎵', '💻', '🌍',
            '⚽', '🏃', '🎯', '🚀', '💡', '🔥', '⭐', '✨', '🏆', '🎪'
        ]
        
        emoji_buttons = ''.join([
            f'<button type="button" class="emoji-btn" data-emoji="{emoji}" onclick="selectEmoji(\'{attrs.get("id", name)}\', \'{emoji}\')">{emoji}</button>'
            for emoji in emojis
        ])
        
        picker_html = f'''
        <div class="emoji-picker-container">
            {html}
            <div class="emoji-grid">
                {emoji_buttons}
            </div>
        </div>
        '''
        
        return picker_html
    
    class Media:
        css = {
            'all': ('forms/emoji_picker.css',)
        }
        js = ('forms/emoji_picker.js',)

class MicrophoneTextarea(forms.Textarea):
    """
    Widget reutilizable para campos de texto largo con botón de micrófono para dictado por voz.
    """
    def render(self, name, value, attrs=None, renderer=None):
        if attrs is None:
            attrs = {}
        attrs['id'] = attrs.get('id', f'id_{name}')
        textarea_html = super().render(name, value, attrs, renderer)
        button_html = f'''
        <button type="button" class="mic-btn" onclick="startDictation('{attrs['id']}')" title="Dictar por voz" style="margin-left:5px;vertical-align:middle;">
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a1 1 0 1 1 2 0 7 7 0 0 1-6 6.92V21h3a1 1 0 1 1 0 2H8a1 1 0 1 1 0-2h3v-2.08A7 7 0 0 1 5 12a1 1 0 1 1 2 0 5 5 0 0 0 10 0z"/>
            </svg>
        </button>
        '''
        return textarea_html + button_html

# Instrucciones:
# 1. Importa este widget donde lo necesites:
#    from applications.utils.widgets import MicrophoneTextarea
# 2. Úsalo en tus ModelForms para los campos largos.
# 3. Agrega el script de startDictation en tu template base.
