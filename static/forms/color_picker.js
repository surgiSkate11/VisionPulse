document.addEventListener('DOMContentLoaded', function() {
    // Manejar color pickers
    const colorPickers = document.querySelectorAll('.color-picker');
    
    colorPickers.forEach(picker => {
        // Crear preview si no existe
        if (!picker.nextElementSibling || !picker.nextElementSibling.classList.contains('color-preview')) {
            const preview = document.createElement('div');
            preview.className = 'color-preview';
            preview.style.backgroundColor = picker.value || '#007bff';
            picker.parentNode.insertBefore(preview, picker.nextSibling);
        }
        
        const preview = picker.nextElementSibling;
        
        // Actualizar preview cuando cambie el color
        picker.addEventListener('input', function() {
            preview.style.backgroundColor = this.value;
        });
        
        picker.addEventListener('change', function() {
            preview.style.backgroundColor = this.value;
        });
    });
});
