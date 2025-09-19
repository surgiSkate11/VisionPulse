/**
 * Notion-style Icon Picker - Componente Reutilizable
 * Permite seleccionar emojis, iconos FontAwesome y subir imágenes personalizadas
 */

class NotionIconPicker {
    constructor(inputElement, options = {}) {
        this.input = inputElement;
        this.options = {
            allowEmojis: true,
            allowIcons: true,
            allowUpload: true,
            position: 'bottom-left',
            maxFileSize: 5 * 1024 * 1024, // 5MB
            ...options
        };
        
        this.picker = null;
        this.currentTab = 'emojis';
        this.isOpen = false;
        
        this.init();
    }
    
    init() {
        this.createPicker();
        this.bindEvents();
        this.loadEmojis();
        this.loadIcons();
    }
    
    createPicker() {
        // Hacer el contenedor relativo
        const container = this.input.closest('.emoji-picker-container') || this.input.parentNode;
        if (container) {
            container.style.position = 'relative';
        }
        
        this.picker = document.createElement('div');
        this.picker.className = 'notion-icon-picker';
        this.picker.innerHTML = this.getPickerHTML();
        
        container.appendChild(this.picker);
        
        // Bind tab events
        this.bindTabEvents();
        this.bindSearchEvents();
        this.bindUploadEvents();
    }
    
    getPickerHTML() {
        return `
            <div class="notion-picker-header">
                <div class="notion-picker-tabs">
                    ${this.options.allowEmojis ? '<button class="notion-picker-tab active" data-tab="emojis">😊 Emojis</button>' : ''}
                    ${this.options.allowIcons ? '<button class="notion-picker-tab" data-tab="icons">🎨 Iconos</button>' : ''}
                    ${this.options.allowUpload ? '<button class="notion-picker-tab" data-tab="upload">📁 Subir</button>' : ''}
                </div>
            </div>
            
            <div class="notion-picker-content">
                ${this.options.allowEmojis ? this.getEmojiTabHTML() : ''}
                ${this.options.allowIcons ? this.getIconTabHTML() : ''}
                ${this.options.allowUpload ? this.getUploadTabHTML() : ''}
            </div>
        `;
    }
    
    getEmojiTabHTML() {
        return `
            <div class="notion-picker-tab-content" data-content="emojis">
                <div class="notion-picker-search-container">
                    <input type="text" class="notion-picker-search" data-search="emojis" placeholder="Buscar emojis..." autocomplete="off">
                </div>
                <div class="emojis-sections"></div>
            </div>
        `;
    }
    
    getIconTabHTML() {
        return `
            <div class="notion-picker-tab-content" data-content="icons" style="display: none;">
                <div class="notion-picker-search-container">
                    <input type="text" class="notion-picker-search" data-search="icons" placeholder="Buscar iconos..." autocomplete="off">
                </div>
                <div class="icons-sections"></div>
            </div>
        `;
    }
    
    getUploadTabHTML() {
        return `
            <div class="notion-picker-tab-content" data-content="upload" style="display: none;">
                <div class="notion-picker-upload-area" data-upload-area>
                    <div class="notion-picker-upload-icon">☁️</div>
                    <div class="notion-picker-upload-text">
                        <strong>Haz clic para subir</strong> o arrastra una imagen aquí
                    </div>
                    <div class="notion-picker-upload-info">
                        PNG, JPG, GIF hasta ${this.formatFileSize(this.options.maxFileSize)}
                    </div>
                </div>
                <input type="file" data-file-input accept="image/*" style="display: none;">
            </div>
        `;
    }
    
    bindEvents() {
        // Click en el input para abrir/cerrar
        this.input.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.toggle();
        });
        
        // Cerrar al hacer click fuera
        document.addEventListener('click', (e) => {
            if (this.isOpen && !this.picker.contains(e.target) && !this.input.contains(e.target)) {
                this.close();
            }
        });
        
        // Manejar teclas Escape para cerrar
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });
    }
    
    bindTabEvents() {
        const tabs = this.picker.querySelectorAll('.notion-picker-tab');
        const contents = this.picker.querySelectorAll('.notion-picker-tab-content');
        
        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const tabId = tab.dataset.tab;
                
                // Update active tab
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                
                // Show corresponding content
                contents.forEach(content => {
                    content.style.display = content.dataset.content === tabId ? 'block' : 'none';
                });
                
                this.currentTab = tabId;
                
                // Focus en el search del nuevo tab activo
                const activeSearch = this.picker.querySelector(`.notion-picker-search[data-search="${tabId}"]`);
                if (activeSearch) {
                    setTimeout(() => {
                        activeSearch.focus();
                        activeSearch.value = '';
                    }, 50);
                }
                
                // Resetear filtros del tab anterior
                this.resetFilters(tabId);
                
                // Resetear scroll al cambiar de tab
                const contentContainer = this.picker.querySelector('.notion-picker-content');
                if (contentContainer) {
                    contentContainer.scrollTop = 0;
                }
                
                return false;
            });
        });
    }
    
    bindSearchEvents() {
        const searches = this.picker.querySelectorAll('.notion-picker-search');
        
        searches.forEach(search => {
            let searchTimeout;
            search.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    const query = e.target.value.toLowerCase().trim();
                    const type = e.target.dataset.search;
                    this.filterItems(type, query);
                }, 100);
            });
            
            search.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    return false;
                }
            });
            
            search.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    e.target.value = '';
                    const type = e.target.dataset.search;
                    this.filterItems(type, '');
                }
            });
        });
    }
    
    bindUploadEvents() {
        const uploadArea = this.picker.querySelector('[data-upload-area]');
        const fileInput = this.picker.querySelector('[data-file-input]');
        
        if (uploadArea && fileInput) {
            uploadArea.addEventListener('click', () => {
                fileInput.click();
            });
            
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });
            
            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });
            
            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    this.handleFileUpload(files[0]);
                }
            });
            
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.handleFileUpload(e.target.files[0]);
                }
            });
        }
    }
    
    loadEmojis() {
        const emojiSections = this.picker.querySelector('.emojis-sections');
        if (!emojiSections) return;
        
        const emojiCategories = {
            'Educación': [
                {emoji: '📚', name: 'libro'},
                {emoji: '📖', name: 'lectura'},
                {emoji: '✏️', name: 'lapiz'},
                {emoji: '📝', name: 'escribir'},
                {emoji: '🔬', name: 'ciencia'},
                {emoji: '🧪', name: 'laboratorio'},
                {emoji: '📐', name: 'regla'},
                {emoji: '📏', name: 'medida'},
                {emoji: '🔍', name: 'buscar'},
                {emoji: '💡', name: 'idea'},
                {emoji: '🎓', name: 'graduacion'},
                {emoji: '🏫', name: 'escuela'},
                {emoji: '🎒', name: 'mochila'},
                {emoji: '📊', name: 'grafico'},
                {emoji: '📈', name: 'estadistica'}
            ],
            'Deportes': [
                {emoji: '⚽', name: 'futbol'},
                {emoji: '🏀', name: 'baloncesto'},
                {emoji: '🏈', name: 'americano'},
                {emoji: '⚾', name: 'baseball'},
                {emoji: '🎾', name: 'tenis'},
                {emoji: '🏐', name: 'voleibol'},
                {emoji: '🏓', name: 'pingpong'},
                {emoji: '🥅', name: 'porteria'},
                {emoji: '🏆', name: 'trofeo'},
                {emoji: '🥇', name: 'medalla'},
                {emoji: '🏃', name: 'correr'},
                {emoji: '🚴', name: 'bicicleta'},
                {emoji: '🏊', name: 'nadar'},
                {emoji: '🤸', name: 'gimnasia'},
                {emoji: '🧗', name: 'escalar'}
            ],
            'Símbolos': [
                {emoji: '❤️', name: 'corazon'},
                {emoji: '💖', name: 'amor'},
                {emoji: '💕', name: 'romance'},
                {emoji: '💓', name: 'latido'},
                {emoji: '💗', name: 'emocion'},
                {emoji: '💘', name: 'cupido'},
                {emoji: '💝', name: 'regalo'},
                {emoji: '💟', name: 'simbolo'},
                {emoji: '♥️', name: 'naipe'},
                {emoji: '💔', name: 'roto'},
                {emoji: '🧡', name: 'naranja'},
                {emoji: '💛', name: 'amarillo'},
                {emoji: '💚', name: 'verde'},
                {emoji: '💙', name: 'azul'},
                {emoji: '💜', name: 'morado'}
            ],
            'Caras': [
                {emoji: '😀', name: 'sonrisa'},
                {emoji: '😃', name: 'feliz'},
                {emoji: '😄', name: 'alegre'},
                {emoji: '😁', name: 'radiante'},
                {emoji: '😆', name: 'risa'},
                {emoji: '😅', name: 'nervioso'},
                {emoji: '🤣', name: 'carcajada'},
                {emoji: '😂', name: 'llorar'},
                {emoji: '🙂', name: 'contento'},
                {emoji: '🙃', name: 'invertida'},
                {emoji: '😉', name: 'guiño'},
                {emoji: '😊', name: 'timido'},
                {emoji: '😇', name: 'angel'},
                {emoji: '🥰', name: 'enamorado'},
                {emoji: '😍', name: 'admiracion'}
            ],
            'Comida': [
                {emoji: '🍎', name: 'manzana'},
                {emoji: '🍌', name: 'banana'},
                {emoji: '🍇', name: 'uvas'},
                {emoji: '🍓', name: 'fresa'},
                {emoji: '🥝', name: 'kiwi'},
                {emoji: '🍑', name: 'cereza'},
                {emoji: '🥥', name: 'coco'},
                {emoji: '🍍', name: 'piña'},
                {emoji: '🥭', name: 'mango'},
                {emoji: '🍒', name: 'cerezas'},
                {emoji: '🍈', name: 'melon'},
                {emoji: '🍉', name: 'sandia'},
                {emoji: '🥑', name: 'aguacate'},
                {emoji: '🍕', name: 'pizza'},
                {emoji: '🍔', name: 'hamburguesa'}
            ],
            'Animales': [
                {emoji: '🐶', name: 'perro'},
                {emoji: '🐱', name: 'gato'},
                {emoji: '🐭', name: 'raton'},
                {emoji: '🐹', name: 'hamster'},
                {emoji: '🐰', name: 'conejo'},
                {emoji: '🦊', name: 'zorro'},
                {emoji: '🐻', name: 'oso'},
                {emoji: '🐼', name: 'panda'},
                {emoji: '🐨', name: 'koala'},
                {emoji: '🐯', name: 'tigre'},
                {emoji: '🦁', name: 'leon'},
                {emoji: '🐮', name: 'vaca'},
                {emoji: '🐷', name: 'cerdo'},
                {emoji: '🐽', name: 'hocico'},
                {emoji: '🐸', name: 'rana'}
            ]
        };
        
        Object.entries(emojiCategories).forEach(([category, emojis]) => {
            const section = document.createElement('div');
            section.className = 'notion-picker-section';
            section.innerHTML = `
                <div class="notion-picker-section-title">${category}</div>
                <div class="notion-picker-grid">
                    ${emojis.map(item => `
                        <button type="button" class="notion-picker-item" 
                                data-emoji="${item.emoji}" 
                                data-name="${item.name}"
                                title="${item.emoji} - ${item.name}">
                            ${item.emoji}
                        </button>
                    `).join('')}
                </div>
            `;
            
            emojiSections.appendChild(section);
        });
        
        // Bind emoji click events
        emojiSections.querySelectorAll('[data-emoji]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.selectEmoji(btn.dataset.emoji);
                return false;
            });
        });
    }
    
    loadIcons() {
        const iconSections = this.picker.querySelector('.icons-sections');
        if (!iconSections) return;
        
        const iconCategories = {
            'Educación': [
                {icon: 'fas fa-graduation-cap', name: 'graduacion', display: '🎓'},
                {icon: 'fas fa-book', name: 'libro', display: '📚'},
                {icon: 'fas fa-pencil-alt', name: 'lapiz', display: '✏️'},
                {icon: 'fas fa-calculator', name: 'calculadora', display: '🧮'},
                {icon: 'fas fa-microscope', name: 'microscopio', display: '🔬'}
            ],
            'Tecnología': [
                {icon: 'fas fa-laptop', name: 'laptop', display: '💻'},
                {icon: 'fas fa-mobile-alt', name: 'movil', display: '📱'},
                {icon: 'fas fa-code', name: 'codigo', display: '</>'}, 
                {icon: 'fas fa-database', name: 'base datos', display: '🗄️'},
                {icon: 'fas fa-server', name: 'servidor', display: '🖥️'}
            ],
            'Negocios': [
                {icon: 'fas fa-briefcase', name: 'maletin', display: '💼'},
                {icon: 'fas fa-chart-line', name: 'grafico', display: '📈'},
                {icon: 'fas fa-dollar-sign', name: 'dinero', display: '💲'},
                {icon: 'fas fa-handshake', name: 'acuerdo', display: '🤝'},
                {icon: 'fas fa-trophy', name: 'trofeo', display: '🏆'}
            ],
            'Comunicación': [
                {icon: 'fas fa-phone', name: 'telefono', display: '📞'},
                {icon: 'fas fa-envelope', name: 'correo', display: '✉️'},
                {icon: 'fas fa-comment', name: 'comentario', display: '💬'},
                {icon: 'fas fa-video', name: 'video', display: '🎥'},
                {icon: 'fas fa-microphone', name: 'microfono', display: '🎤'}
            ]
        };
        
        Object.entries(iconCategories).forEach(([category, icons]) => {
            const section = document.createElement('div');
            section.className = 'notion-picker-section';
            section.innerHTML = `
                <div class="notion-picker-section-title">${category}</div>
                <div class="notion-picker-grid">
                    ${icons.map(item => `
                        <button type="button" class="notion-picker-item" 
                                data-icon="${item.icon}" 
                                data-name="${item.name}"
                                data-display="${item.display}"
                                title="${item.name}">
                            <i class="${item.icon}"></i>
                        </button>
                    `).join('')}
                </div>
            `;
            
            iconSections.appendChild(section);
        });
        
        // Bind icon click events
        iconSections.querySelectorAll('[data-icon]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.selectIcon(btn.dataset.display || btn.dataset.icon, btn.dataset.name);
                return false;
            });
        });
    }
    
    selectEmoji(emoji) {
        this.input.value = emoji;
        this.triggerChange();
        this.close();
    }
    
    selectIcon(iconDisplay, iconName) {
        // Mostrar el emoji/símbolo visual en lugar del código FontAwesome
        this.input.value = iconDisplay;
        this.triggerChange();
        this.close();
    }
    
    handleFileUpload(file) {
        if (file.size > this.options.maxFileSize) {
            alert(`El archivo es muy grande. Máximo ${this.formatFileSize(this.options.maxFileSize)}`);
            return;
        }
        
        if (!file.type.startsWith('image/')) {
            alert('Solo se permiten imágenes');
            return;
        }
        
        const reader = new FileReader();
        reader.onload = (e) => {
            this.showImagePreview(e.target.result);
            this.input.value = e.target.result;
            this.triggerChange();
            this.close();
        };
        reader.readAsDataURL(file);
    }
    
    showImagePreview(imageSrc) {
        const container = this.input.parentNode;
        
        const existingPreview = container.querySelector('.notion-picker-preview');
        if (existingPreview) {
            existingPreview.remove();
        }
        
        const preview = document.createElement('img');
        preview.src = imageSrc;
        preview.className = 'notion-picker-preview';
        preview.style.marginLeft = '8px';
        
        container.appendChild(preview);
        this.input.style.display = 'none';
    }
    
    filterItems(type, query) {
        const container = this.picker.querySelector(`.${type}-sections`);
        if (!container) return;
        
        const items = container.querySelectorAll('.notion-picker-item');
        let visibleCount = 0;
        
        items.forEach(item => {
            let matches = true;
            
            if (query) {
                const searchQuery = query.toLowerCase().trim();
                
                if (type === 'emojis') {
                    const emoji = item.dataset.emoji || item.textContent.trim();
                    const name = (item.dataset.name || '').toLowerCase();
                    matches = emoji.includes(searchQuery) || name.includes(searchQuery);
                } else if (type === 'icons') {
                    const name = (item.dataset.name || '').toLowerCase();
                    matches = name.includes(searchQuery);
                }
            }
            
            item.style.display = matches ? 'flex' : 'none';
            if (matches) visibleCount++;
        });
        
        const sections = container.querySelectorAll('.notion-picker-section');
        sections.forEach(section => {
            const visibleItems = section.querySelectorAll('.notion-picker-item[style*="flex"], .notion-picker-item:not([style*="none"])');
            const hasVisibleItems = Array.from(visibleItems).some(item => 
                item.style.display !== 'none'
            );
            section.style.display = hasVisibleItems ? 'block' : 'none';
        });
        
        this.toggleNoResultsMessage(container, visibleCount === 0 && query);
    }
    
    toggleNoResultsMessage(container, show) {
        let message = container.querySelector('.notion-picker-no-results');
        
        if (show) {
            if (!message) {
                message = document.createElement('div');
                message.className = 'notion-picker-no-results';
                message.innerHTML = `
                    <div class="notion-picker-no-results-icon">🔍</div>
                    <div class="notion-picker-no-results-text">No se encontraron resultados</div>
                `;
                container.appendChild(message);
            }
            message.style.display = 'flex';
        } else if (message) {
            message.style.display = 'none';
        }
    }
    
    resetFilters(tabId) {
        const container = this.picker.querySelector(`.${tabId}-sections`);
        if (!container) return;
        
        const items = container.querySelectorAll('.notion-picker-item');
        items.forEach(item => {
            item.style.display = 'flex';
        });
        
        const sections = container.querySelectorAll('.notion-picker-section');
        sections.forEach(section => {
            section.style.display = 'block';
        });
        
        this.toggleNoResultsMessage(container, false);
    }
    
    triggerChange() {
        const event = new Event('change', { bubbles: true });
        this.input.dispatchEvent(event);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    toggle() {
        this.isOpen ? this.close() : this.open();
    }
    
    open() {
        this.picker.style.display = 'block';
        this.picker.classList.add('show');
        this.isOpen = true;
        
        // Asegurar que el scroll esté en el top
        const contentContainer = this.picker.querySelector('.notion-picker-content');
        if (contentContainer) {
            contentContainer.scrollTop = 0;
        }
        
        setTimeout(() => {
            const activeSearch = this.picker.querySelector(`.notion-picker-search[data-search="${this.currentTab}"]`);
            if (activeSearch) {
                activeSearch.focus();
            }
        }, 50);
    }

    close() {
        this.picker.style.display = 'none';
        this.picker.classList.remove('show');
        this.isOpen = false;
    }    destroy() {
        if (this.picker && this.picker.parentNode) {
            this.picker.parentNode.removeChild(this.picker);
        }
    }
}

// Función de utilidad para inicializar automáticamente
function initNotionIconPickers() {
    document.querySelectorAll('.emoji-input').forEach(input => {
        if (!input.notionPicker) {
            input.notionPicker = new NotionIconPicker(input);
        }
    });
}

// Auto-inicializar al cargar el DOM
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNotionIconPickers);
} else {
    initNotionIconPickers();
}