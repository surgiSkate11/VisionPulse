// Búsqueda en tiempo real de medicamentos (AJAX)
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.querySelector('.premium-search-input');
    const tablaBody = document.getElementById('tabla-medicamentos-body');
    let searchTimeout = null;

    if (searchInput && tablaBody) {
        searchInput.addEventListener('input', function() {
            const query = this.value.trim();
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                fetch(`/core/medicamento/search/?q="${encodeURIComponent(query)}"`)
                    .then(response => response.json())
                    .then(data => {
                        tablaBody.innerHTML = '';
                        if (data.medicamentos.length === 0) {
                            tablaBody.innerHTML = `<tr><td colspan="7" class="px-8 py-16 text-center text-gray-400">No hay medicamentos encontrados</td></tr>`;
                        } else {
                            data.medicamentos.forEach(medicamento => {
                                tablaBody.innerHTML += `
<tr class="table-row-hover">
    <td class="premium-cell">
        <div class="flex items-center space-x-4">
            <div class="premium-icon-container">
                <i class="fas fa-capsules"></i>
            </div>
            <div>
                <div class="text-lg font-bold text-[var(--text-dark)] mb-1">${medicamento.nombre}</div>
            </div>
        </div>
    </td>
    <td class="premium-cell text-center">${medicamento.tipo}</td>
    <td class="premium-cell text-center">${medicamento.marca}</td>
    <td class="premium-cell text-center">${medicamento.cantidad ?? '-'}</td>
    <td class="premium-cell text-center">$${medicamento.precio}</td>
    <td class="premium-cell text-center">
        ${medicamento.disponible ? `<span class='premium-badge bg-green-100 text-green-700'><i class='fas fa-check-circle mr-1'></i>Disponible</span>` : `<span class='premium-badge bg-red-100 text-red-700'><i class='fas fa-times-circle mr-1'></i>No disponible</span>`}
    </td>
    <td class="premium-cell text-center">
        <div class="flex flex-row items-center justify-center gap-6">
            <a href="/core/medicamento/${medicamento.id}/editar/"
               class="premium-button !p-3 !bg-[var(--aurora2)]/10 hover:!bg-[var(--aurora2)]/20 !shadow-none rounded-full transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[var(--aurora2)]"
               title="Editar">
                <i class="fas fa-pen-to-square text-[var(--aurora1)] text-xl"></i>
            </a>
            <a href="#"
               class="premium-button !p-3 !bg-red-100 hover:!bg-red-200 !shadow-none rounded-full transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-300"
               onclick="openDeleteModal('${medicamento.id}', '${medicamento.nombre}')"
               title="Eliminar">
                <i class="fas fa-trash-can text-red-600 text-xl"></i>
            </a>
        </div>
    </td>
</tr>`;
                            });
                        }
                    });
            }, 250); // Debounce
        });
    }
});
