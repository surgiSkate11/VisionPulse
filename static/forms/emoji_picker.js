function selectEmoji(fieldId, emoji) {
    const field = document.getElementById(fieldId);
    if (field) {
        field.value = emoji;
        field.dispatchEvent(new Event('change'));
        
        // Ocultar el grid después de seleccionar
        const container = field.closest('.emoji-picker-container');
        if (container) {
            const grid = container.querySelector('.emoji-grid');
            if (grid) {
                grid.style.display = 'none';
                setTimeout(() => {
                    grid.style.display = '';
                }, 200);
            }
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Manejar clics fuera del emoji picker para cerrarlo
    document.addEventListener('click', function(event) {
        if (!event.target.closest('.emoji-picker-container')) {
            const grids = document.querySelectorAll('.emoji-grid');
            grids.forEach(grid => {
                grid.style.display = 'none';
                setTimeout(() => {
                    grid.style.display = '';
                }, 200);
            });
        }
    });
    
    // Prevenir que el clic en emoji buttons cierre el form
    document.querySelectorAll('.emoji-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
        });
    });
});
