document.addEventListener('DOMContentLoaded', () => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
    }

    const initData = tg?.initData || '';
    
    let tasks = [];
    let currentFilter = 'all';
    let currentCalDate = new Date();
    let selectedSnoozeTaskId = null;

    // Стан обраних часів та інтервалу для створення
    let selectedTimes = [];
    let selectedInterval = 0;

    // Стан для редагування
    let editSelectedTimes = [];
    let editSelectedInterval = 0;

    function getLocalDateISO(d = new Date()) {
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    if (tg?.initDataUnsafe?.user) {
        const user = tg.initDataUnsafe.user;
        const nameEl = document.getElementById('user-name');
        if (nameEl) nameEl.textContent = `${user.first_name || ''} ${user.last_name || ''}`.trim() || 'Користувач';

        const avatarEl = document.getElementById('user-avatar');
        if (avatarEl) {
            if (user.photo_url) {
                avatarEl.innerHTML = `<img src="${user.photo_url}" alt="Avatar" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;">`;
            } else {
                const initial = (user.first_name || 'U').charAt(0).toUpperCase();
                avatarEl.textContent = initial;
            }
        }
    }


    async function apiRequest(url, options = {}) {
        options.headers = options.headers || {};
        options.headers['X-Telegram-Init-Data'] = initData;
        options.headers['Content-Type'] = 'application/json';
        options.headers['Bypass-Tunnel-Reminder'] = 'true';
        options.headers['Ngrok-Skip-Browser-Warning'] = 'true';

        try {
            const res = await fetch(url, options);
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || `Помилка ${res.status}`);
            }
            return await res.json();
        } catch (err) {
            showToast(`❌ ${err.message}`);
            throw err;
        }
    }

    function showToast(msg) {
        const toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 3500);
    }

    // Bottom Nav
    const navItems = document.querySelectorAll('.nav-item');
    const tabPanes = document.querySelectorAll('.tab-pane');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetTab = item.dataset.tab;
            navItems.forEach(n => n.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            item.classList.add('active');
            const targetPane = document.getElementById(`tab-${targetTab}`);
            if (targetPane) targetPane.classList.add('active');

            if (targetTab === 'calendar') {
                renderCalendar();
            }
        });
    });

    // Modals
    const createModal = document.getElementById('create-modal');
    const fabBtn = document.getElementById('fab-add-btn');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const timePicker = document.getElementById('task-time-picker');
    const datePicker = document.getElementById('task-date-picker');

    if (fabBtn) {
        fabBtn.addEventListener('click', () => {
            const now = new Date();
            const defaultTime = "09:00";
            
            if (timePicker) timePicker.value = defaultTime;
            selectedTimes = [defaultTime];
            
            if (datePicker && !datePicker.value) {
                datePicker.value = getLocalDateISO(now);
            }

            renderTimeTags();
            if (createModal) createModal.classList.remove('hidden');
        });
    }


    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', () => {
            if (createModal) createModal.classList.add('hidden');
        });
    }

    const editModal = document.getElementById('edit-modal');
    const closeEditModalBtn = document.getElementById('close-edit-modal-btn');
    if (closeEditModalBtn) {
        closeEditModalBtn.addEventListener('click', () => {
            if (editModal) editModal.classList.add('hidden');
        });
    }

    const snoozeModal = document.getElementById('snooze-modal');
    const closeSnoozeModalBtn = document.getElementById('close-snooze-modal-btn');
    const snoozeAllBtn = document.getElementById('snooze-all-btn');

    if (closeSnoozeModalBtn) {
        closeSnoozeModalBtn.addEventListener('click', () => {
            if (snoozeModal) snoozeModal.classList.add('hidden');
        });
    }

    if (snoozeAllBtn) {
        snoozeAllBtn.addEventListener('click', () => {
            selectedSnoozeTaskId = null;
            const titleEl = document.getElementById('snooze-modal-title');
            if (titleEl) titleEl.textContent = '⏸ Відкласти ВСІ нагадування';
            if (snoozeModal) snoozeModal.classList.remove('hidden');
        });
    }

    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', loadTasks);

    // Зміна значення у Time Picker оновлює текст на кнопці "➕ Додати"
    if (timePicker) {
        timePicker.addEventListener('change', (e) => {
            const val = e.target.value;
            const addBtn = document.getElementById('add-time-btn');
            if (addBtn && val) {
                addBtn.textContent = `➕ Додати ${val}`;
            }
        });
    }


    // Рендеринг тегів часів (Створення)
    function renderTimeTags() {
        const container = document.getElementById('selected-times-container');
        if (!container) return;
        container.innerHTML = '';

        selectedTimes.sort();

        selectedTimes.forEach(t => {
            const tag = document.createElement('span');
            tag.className = 'tag-item';
            tag.innerHTML = `🕒 ${t} <span class="remove-tag" data-time="${t}">❌</span>`;
            container.appendChild(tag);
        });

        // Підсвічуємо активні чіпи
        document.querySelectorAll('.time-preset-chip').forEach(chip => {
            const t = chip.dataset.time;
            chip.classList.toggle('active', selectedTimes.includes(t));
        });

        container.querySelectorAll('.remove-tag').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const timeToRemove = e.currentTarget.dataset.time;
                selectedTimes = selectedTimes.filter(t => t !== timeToRemove);
                if (selectedTimes.length === 0 && timePicker) {
                    selectedTimes = [timePicker.value || '09:00'];
                }
                renderTimeTags();
            });
        });
    }

    // Додавання часу з Time Picker та Preset Chips
    const addTimeBtn = document.getElementById('add-time-btn');
    if (addTimeBtn) {
        addTimeBtn.addEventListener('click', () => {
            const val = timePicker ? timePicker.value : null;
            if (val && !selectedTimes.includes(val)) {
                selectedTimes.push(val);
                selectedTimes.sort();
                renderTimeTags();
            }
        });
    }

    document.querySelectorAll('.time-preset-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            const t = e.currentTarget.dataset.time;
            if (t) {
                if (selectedTimes.includes(t)) {
                    if (selectedTimes.length > 1) {
                        selectedTimes = selectedTimes.filter(item => item !== t);
                    }
                } else {
                    selectedTimes.push(t);
                    selectedTimes.sort();
                }
                if (timePicker) timePicker.value = t;
                renderTimeTags();
            }
        });
    });


    // Швидкі пресети дати
    document.getElementById('preset-today')?.addEventListener('click', () => {
        if (datePicker) datePicker.value = getLocalDateISO(new Date());
    });

    document.getElementById('preset-tomorrow')?.addEventListener('click', () => {
        const tom = new Date();
        tom.setDate(tom.getDate() + 1);
        if (datePicker) datePicker.value = getLocalDateISO(tom);
    });

    document.getElementById('preset-in3days')?.addEventListener('click', () => {
        const d3 = new Date();
        d3.setDate(d3.getDate() + 3);
        if (datePicker) datePicker.value = getLocalDateISO(d3);
    });

    // Графічні чіпи інтервалу (Створення)
    const intervalChips = document.querySelectorAll('.interval-chip:not(.edit-interval-chip)');
    intervalChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            intervalChips.forEach(c => c.classList.remove('active'));
            e.currentTarget.classList.add('active');
            selectedInterval = parseInt(e.currentTarget.dataset.minutes) || 0;
        });
    });
    // Завантаження завдань з API
    async function loadTasks() {
        try {
            const data = await apiRequest('/api/tasks');
            tasks = data.tasks || [];

            // Оновити лічильник та прогрес
            const countEl = document.getElementById('tasks-count');
            if (countEl) countEl.textContent = `${tasks.length} активних нагадувань`;

            const progressEl = document.getElementById('progress-percent');
            if (progressEl) progressEl.textContent = `${data.progress_percent || 0}%`;

            const progressBar = document.getElementById('progress-bar-fill');
            if (progressBar) progressBar.style.width = `${data.progress_percent || 0}%`;

            renderTaskList();
        } catch (err) {
            console.error('loadTasks error:', err);
        }
    }

    // Рендеринг завдань
    function renderTaskList() {
        const container = document.getElementById('tasks-container');
        if (!container) return;
        container.innerHTML = '';

        const todayIndex = (new Date().getDay() === 0) ? 6 : new Date().getDay() - 1;

        const filtered = tasks.filter(t => {
            if (currentFilter === 'today') {
                return !t.is_one_time && t.days.includes(todayIndex);
            }
            if (currentFilter === 'daily') return !t.is_one_time;
            if (currentFilter === 'onetime') return t.is_one_time;
            return true;
        });

        if (filtered.length === 0) {
            container.innerHTML = '<div class="loading-spinner">Немає активних нагадувань 🎯</div>';
            return;
        }

        const daysNames = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд'];

        filtered.forEach(task => {
            const card = document.createElement('div');
            card.className = `task-card ${task.is_one_time ? 'one-time' : ''}`;

            let daysText = 'Щодня';
            if (task.is_one_time) {
                daysText = task.one_time_date ? `Дата: ${task.one_time_date}` : 'Одноразове';
            } else if (task.days && task.days.length < 7) {
                daysText = task.days.map(d => daysNames[d]).join(', ');
            }

            let timeSlotsHtml = '';
            if (task.time_statuses && task.time_statuses.length > 0) {
                timeSlotsHtml = task.time_statuses.map(st => {
                    let icon = '🕒';
                    if (st.status === 'completed') icon = '✅';
                    else if (st.status === 'next') icon = '⏳';
                    else if (st.status === 'past') icon = '⚠️';
                    
                    const tClean = st.time.replace(':', '');
                    const instId = `${task.task_id}_${tClean}`;
                    return `<span class="time-slot-chip ${st.status}" data-task-id="${task.task_id}" data-inst-id="${instId}" title="${st.label}">
                        ${icon} ${st.time} <span class="time-slot-label">(${st.label})</span>
                    </span>`;
                }).join('');
            } else {
                timeSlotsHtml = (task.times || []).map(t => `<span class="time-slot-chip upcoming">🕒 ${t}</span>`).join('');
            }

            card.innerHTML = `
                <div class="task-header">
                    <div class="task-title">${escapeHtml(task.description)}</div>
                    <span class="task-badge">${task.is_one_time ? 'Одноразове' : 'Повторюване'}</span>
                </div>
                <div class="task-details">
                    <div class="time-slots-wrapper">
                        <span class="time-slots-title">🕒 Час:</span>
                        ${timeSlotsHtml}
                    </div>
                    <div class="task-detail-item">📅 ${daysText}</div>
                    ${task.interval_minutes > 0 ? `<div class="task-detail-item">🔄 кожні ${task.interval_minutes} хв</div>` : ''}
                </div>
                <div class="task-actions">
                    <button class="btn-small btn-success complete-btn" data-id="${task.task_id}">✅ Готово</button>
                    <button class="btn-small btn-primary snooze-btn" data-id="${task.task_id}">⏸ Відкласти</button>
                    <button class="btn-small btn-secondary edit-btn" data-id="${task.task_id}">✏️ Редагувати</button>
                    <button class="btn-small btn-danger delete-btn" data-id="${task.task_id}">🗑 Видалити</button>
                </div>
            `;

            container.appendChild(card);
        });

        // Слухачі для тапу по слоту часу
        container.querySelectorAll('.time-slot-chip:not(.completed)').forEach(chip => {
            chip.addEventListener('click', async (e) => {
                const taskId = e.currentTarget.dataset.taskId;
                const instId = e.currentTarget.dataset.instId;
                if (!taskId) return;

                try {
                    await apiRequest(`/api/tasks/${taskId}/complete`, {
                        method: 'POST',
                        body: JSON.stringify({ reminder_instance_id: instId })
                    });
                    showToast('✅ Слот часу відмічено виконаним!');
                    loadTasks();
                } catch (err) {
                    console.error('Time slot complete error:', err);
                }
            });
        });

        container.querySelectorAll('.complete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const taskId = parseInt(e.currentTarget.dataset.id);
                const task = tasks.find(t => t.task_id === taskId);
                
                let instId = null;
                if (task && task.time_statuses) {
                    const activeSlot = task.time_statuses.find(st => st.status === 'next') || 
                                       task.time_statuses.find(st => st.status === 'past') ||
                                       task.time_statuses.find(st => st.status !== 'completed');
                    if (activeSlot) {
                        const tClean = activeSlot.time.replace(':', '');
                        instId = `${taskId}_${tClean}`;
                    }
                }

                await apiRequest(`/api/tasks/${taskId}/complete`, { 
                    method: 'POST', 
                    body: JSON.stringify(instId ? { reminder_instance_id: instId } : {}) 
                });
                showToast('✅ Слот часу відмічено виконаним!');
                loadTasks();
            });
        });

        container.querySelectorAll('.snooze-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                selectedSnoozeTaskId = e.currentTarget.dataset.id;
                const titleEl = document.getElementById('snooze-modal-title');
                if (titleEl) titleEl.textContent = '⏸ Відкласти нагадування';
                if (snoozeModal) snoozeModal.classList.remove('hidden');
            });
        });

        container.querySelectorAll('.edit-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const taskId = parseInt(e.currentTarget.dataset.id);
                openEditModal(taskId);
            });
        });

        container.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const taskId = e.currentTarget.dataset.id;
                if (confirm('Видалити це нагадування?')) {
                    try {
                        await apiRequest(`/api/tasks/${taskId}/delete`, { method: 'POST' });
                        showToast('🗑 Нагадування видалено');
                        loadTasks();
                    } catch (err) {
                        showToast(`❌ Помилка видалення: ${err.message}`);
                    }
                }
            });
        });

    }

    // Редагування модалка
    function openEditModal(taskId) {
        const task = tasks.find(t => t.task_id === taskId);
        if (!task) return;

        const editIdEl = document.getElementById('edit-task-id');
        const editDescEl = document.getElementById('edit-task-desc');
        if (editIdEl) editIdEl.value = task.task_id;
        if (editDescEl) editDescEl.value = task.description;

        editSelectedTimes = [...task.times];
        renderEditTimeTags();

        editSelectedInterval = task.interval_minutes || 0;
        document.querySelectorAll('.edit-interval-chip').forEach(chip => {
            const mins = parseInt(chip.dataset.minutes) || 0;
            chip.classList.toggle('active', mins === editSelectedInterval);
        });

        document.querySelectorAll('.edit-day-chip').forEach(chip => {
            const dayVal = parseInt(chip.dataset.day);
            chip.classList.toggle('active', task.days.includes(dayVal));
        });

        if (editModal) editModal.classList.remove('hidden');
    }

    function renderEditTimeTags() {
        const container = document.getElementById('edit-selected-times-container');
        if (!container) return;
        container.innerHTML = '';

        editSelectedTimes.sort();

        editSelectedTimes.forEach(t => {
            const tag = document.createElement('span');
            tag.className = 'tag-item';
            tag.innerHTML = `🕒 ${t} <span class="edit-remove-tag" data-time="${t}">❌</span>`;
            container.appendChild(tag);
        });

        // Підсвічуємо активні чіпи в модалці редагування
        document.querySelectorAll('.edit-time-preset-chip').forEach(chip => {
            const t = chip.dataset.time;
            chip.classList.toggle('active', editSelectedTimes.includes(t));
        });

        container.querySelectorAll('.edit-remove-tag').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const timeToRemove = e.currentTarget.dataset.time;
                editSelectedTimes = editSelectedTimes.filter(t => t !== timeToRemove);
                if (editSelectedTimes.length === 0) {
                    const picker = document.getElementById('edit-task-time-picker');
                    editSelectedTimes = [picker ? picker.value || '09:00' : '09:00'];
                }
                renderEditTimeTags();
            });
        });
    }

    const editAddTimeBtn = document.getElementById('edit-add-time-btn');
    if (editAddTimeBtn) {
        editAddTimeBtn.addEventListener('click', () => {
            const picker = document.getElementById('edit-task-time-picker');
            const val = picker ? picker.value : null;
            if (val && !editSelectedTimes.includes(val)) {
                editSelectedTimes.push(val);
                editSelectedTimes.sort();
                renderEditTimeTags();
            }
        });
    }

    const editTimePicker = document.getElementById('edit-task-time-picker');
    if (editTimePicker) {
        editTimePicker.addEventListener('change', (e) => {
            const val = e.target.value;
            const editBtn = document.getElementById('edit-add-time-btn');
            if (editBtn && val) {
                editBtn.textContent = `➕ Додати ${val}`;
            }
        });
    }


    document.querySelectorAll('.edit-time-preset-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            const t = e.currentTarget.dataset.time;
            if (t) {
                if (editSelectedTimes.includes(t)) {
                    if (editSelectedTimes.length > 1) {
                        editSelectedTimes = editSelectedTimes.filter(item => item !== t);
                    }
                } else {
                    editSelectedTimes.push(t);
                    editSelectedTimes.sort();
                }
                if (editTimePicker) editTimePicker.value = t;
                renderEditTimeTags();
            }
        });
    });


    document.querySelectorAll('.edit-interval-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            document.querySelectorAll('.edit-interval-chip').forEach(c => c.classList.remove('active'));
            e.currentTarget.classList.add('active');
            editSelectedInterval = parseInt(e.currentTarget.dataset.minutes) || 0;
        });
    });

    document.querySelectorAll('.edit-day-chip').forEach(chip => {
        chip.addEventListener('click', (e) => e.currentTarget.classList.toggle('active'));
    });

    const editForm = document.getElementById('edit-task-form');
    if (editForm) {
        editForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const taskId = document.getElementById('edit-task-id').value;
            const description = document.getElementById('edit-task-desc').value.trim();
            const times = editSelectedTimes.length > 0 ? editSelectedTimes : ['09:00'];
            const interval_minutes = editSelectedInterval;

            const days = [];
            document.querySelectorAll('.edit-day-chip.active').forEach(chip => {
                days.push(parseInt(chip.dataset.day));
            });

            try {
                await apiRequest(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    body: JSON.stringify({
                        description,
                        times,
                        interval_minutes,
                        days: days.length > 0 ? days : [0, 1, 2, 3, 4, 5, 6]
                    })
                });

                showToast('✏️ Нагадування відредаговано!');
                if (editModal) editModal.classList.add('hidden');
                loadTasks();
            } catch (err) {
                // Handled
            }
        });
    }

    // Snooze
    document.querySelectorAll('.snooze-opt-btn[data-minutes]').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const minutes = parseInt(e.currentTarget.dataset.minutes);

            if (selectedSnoozeTaskId) {
                await apiRequest(`/api/tasks/${selectedSnoozeTaskId}/snooze`, {
                    method: 'POST',
                    body: JSON.stringify({ minutes })
                });
                showToast(`⏸ Нагадування відкладено на ${minutes} хв`);
            } else {
                await apiRequest('/api/snooze-all', {
                    method: 'POST',
                    body: JSON.stringify({ minutes })
                });
                showToast(`⏸ Усі нагадування відкладено на ${minutes} хв`);
            }

            if (snoozeModal) snoozeModal.classList.add('hidden');
            loadTasks();
        });
    });

    const clearSnoozeBtn = document.getElementById('clear-snooze-btn');
    if (clearSnoozeBtn) {
        clearSnoozeBtn.addEventListener('click', async () => {
            await apiRequest('/api/snooze-clear', { method: 'POST' });
            showToast('▶️ Глобальне відкладення скасовано!');
            if (snoozeModal) snoozeModal.classList.add('hidden');
            loadTasks();
        });
    }

    // Фільтри
    document.querySelectorAll('.filter-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
            e.currentTarget.classList.add('active');
            currentFilter = e.currentTarget.dataset.filter;
            renderTaskList();
        });
    });

    // Форма створення сабміт
    const scheduleTypeRadios = document.querySelectorAll('input[name="schedule_type"]');
    const daysGroup = document.getElementById('days-selector-group');
    const datesGroup = document.getElementById('dates-selector-group');

    scheduleTypeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'onetime') {
                if (daysGroup) daysGroup.classList.add('hidden');
                if (datesGroup) datesGroup.classList.remove('hidden');
            } else {
                if (daysGroup) daysGroup.classList.remove('hidden');
                if (datesGroup) datesGroup.classList.add('hidden');
            }
        });
    });

    const dayChips = document.querySelectorAll('.day-chip:not(.edit-day-chip)');
    dayChips.forEach(chip => chip.addEventListener('click', (e) => e.currentTarget.classList.toggle('active')));

    const createForm = document.getElementById('create-task-form');
    if (createForm) {
        createForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const description = document.getElementById('task-desc').value.trim();
            if (!description) {
                showToast('Введіть опис завдання');
                return;
            }

            const scheduleType = document.querySelector('input[name="schedule_type"]:checked').value;
            const isOneTime = (scheduleType === 'onetime');
            
            let times = [...selectedTimes];
            if (times.length === 0) {
                times = [timePicker ? timePicker.value || '09:00' : '09:00'];
            }


            const interval_minutes = selectedInterval;

            let days = [];
            let one_time_date = null;

            if (isOneTime) {
                one_time_date = datePicker ? datePicker.value : getLocalDateISO();
                days = [0];
            } else {
                dayChips.forEach(chip => {
                    if (chip.classList.contains('active')) days.push(parseInt(chip.dataset.day));
                });
                if (days.length === 0) {
                    days = [0, 1, 2, 3, 4, 5, 6];
                }
            }

            try {
                await apiRequest('/api/tasks', {
                    method: 'POST',
                    body: JSON.stringify({
                        description,
                        days,
                        times,
                        interval_minutes,
                        is_one_time: isOneTime,
                        one_time_date
                    })
                });

                showToast('🎉 Нагадування успішно створено!');
                createForm.reset();
                
                const now = new Date();
                const curTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
                selectedTimes = [curTime];
                if (timePicker) timePicker.value = curTime;
                renderTimeTags();
                
                if (createModal) createModal.classList.add('hidden');
                loadTasks();
            } catch (err) {
                // Handled
            }
        });
    }

    function isTaskOnDate(t, cellDate, dayOfWeek) {
        if (!t.is_one_time && t.days.includes(dayOfWeek)) return true;
        if (t.is_one_time && t.one_time_date) {
            const cellISO = getLocalDateISO(cellDate);
            const dates = t.one_time_date.split(',').map(d => d.trim());
            return dates.some(d => {
                const dClean = d.substring(0, 10);
                if (dClean === cellISO) return true;
                if (dClean.includes('.')) {
                    const parts = dClean.split('.');
                    if (parts.length === 3) {
                        const formatted = `${parts[2]}-${parts[1].padStart(2, '0')}-${parts[0].padStart(2, '0')}`;
                        return formatted === cellISO;
                    }
                }
                return false;
            });
        }
        return false;
    }

    // Календар
    function renderCalendar() {
        const titleEl = document.getElementById('cal-month-title');
        const grid = document.getElementById('calendar-days');
        if (!grid) return;

        const year = currentCalDate.getFullYear();
        const month = currentCalDate.getMonth();
        
        const monthNames = ['Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень', 'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень'];
        if (titleEl) titleEl.textContent = `${monthNames[month]} ${year}`;

        grid.innerHTML = '';

        const firstDayOfMonth = new Date(year, month, 1).getDay();
        const startDayIndex = (firstDayOfMonth === 0) ? 6 : firstDayOfMonth - 1;
        const daysInMonth = new Date(year, month + 1, 0).getDate();

        for (let i = 0; i < startDayIndex; i++) {
            const emptyCell = document.createElement('div');
            emptyCell.className = 'cal-day empty';
            grid.appendChild(emptyCell);
        }

        const today = new Date();
        let selectedCellFound = false;

        for (let d = 1; d <= daysInMonth; d++) {
            const dayCell = document.createElement('div');
            dayCell.className = 'cal-day';
            dayCell.textContent = d;

            const cellDate = new Date(year, month, d);
            const jsDay = cellDate.getDay();
            const dayOfWeek = (jsDay === 0) ? 6 : jsDay - 1;

            const isToday = (today.getFullYear() === year && today.getMonth() === month && today.getDate() === d);
            if (isToday) {
                dayCell.classList.add('today');
                dayCell.classList.add('selected');
                selectedCellFound = true;
                showCalendarDayTasks(cellDate, dayOfWeek);
            }

            const hasTask = tasks.some(t => isTaskOnDate(t, cellDate, dayOfWeek));

            if (hasTask) {
                const dot = document.createElement('span');
                dot.className = 'dot';
                dayCell.appendChild(dot);
            }

            dayCell.addEventListener('click', () => {
                document.querySelectorAll('.cal-day').forEach(c => c.classList.remove('selected'));
                dayCell.classList.add('selected');
                showCalendarDayTasks(cellDate, dayOfWeek);
            });

            grid.appendChild(dayCell);
        }

        if (!selectedCellFound) {
            const firstCell = new Date(year, month, 1);
            const jsDay = firstCell.getDay();
            showCalendarDayTasks(firstCell, (jsDay === 0) ? 6 : jsDay - 1);
        }
    }

    function showCalendarDayTasks(date, dayOfWeek) {
        const title = document.getElementById('selected-date-title');
        const container = document.getElementById('selected-date-tasks');

        const formatted = `${date.getDate()}.${date.getMonth() + 1}.${date.getFullYear()}`;
        if (title) title.textContent = `Нагадування на ${formatted}:`;
        if (!container) return;
        container.innerHTML = '';

        const dayTasks = tasks.filter(t => isTaskOnDate(t, date, dayOfWeek));

        if (dayTasks.length === 0) {
            container.innerHTML = '<div class="loading-spinner">На цей день немає планових завдань</div>';
            return;
        }

        dayTasks.forEach(t => {
            const item = document.createElement('div');
            item.className = 'task-card';
            item.innerHTML = `
                <div class="task-title">${escapeHtml(t.description)}</div>
                <div class="task-details">
                    <div class="task-detail-item">🕒 <strong>${t.times.join(', ')}</strong></div>
                    <div class="task-detail-item">${t.is_one_time ? '📌 Одноразове' : '🔄 Повторюване'}</div>
                </div>
            `;
            container.appendChild(item);
        });
    }


    // Обробка свайпів на Календарі (Touch & Pointer events)
    const calendarCard = document.querySelector('.calendar-card') || document.getElementById('tab-calendar');
    if (calendarCard) {
        let startX = 0;
        let startY = 0;

        const handleStart = (clientX, clientY) => {
            startX = clientX;
            startY = clientY;
        };

        const handleEnd = (clientX, clientY) => {
            const diffX = clientX - startX;
            const diffY = clientY - startY;

            // Горизонтальний свайп (якщо diffX > diffY та більше 35px)
            if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 35) {
                const grid = document.getElementById('calendar-days');
                if (diffX < 0) {
                    // Свайп вліво -> Наступний місяць
                    if (grid) grid.style.animation = 'slideLeft 0.2s ease-out';
                    currentCalDate.setMonth(currentCalDate.getMonth() + 1);
                    setTimeout(() => {
                        renderCalendar();
                        if (grid) grid.style.animation = '';
                    }, 100);
                } else {
                    // Свайп вправо -> Попередній місяць
                    if (grid) grid.style.animation = 'slideRight 0.2s ease-out';
                    currentCalDate.setMonth(currentCalDate.getMonth() - 1);
                    setTimeout(() => {
                        renderCalendar();
                        if (grid) grid.style.animation = '';
                    }, 100);
                }
            }
        };

        // Touch events для мобільних пристроїв
        calendarCard.addEventListener('touchstart', (e) => {
            if (e.touches && e.touches.length > 0) {
                handleStart(e.touches[0].clientX, e.touches[0].clientY);
            }
        }, { passive: true });

        calendarCard.addEventListener('touchend', (e) => {
            if (e.changedTouches && e.changedTouches.length > 0) {
                handleEnd(e.changedTouches[0].clientX, e.changedTouches[0].clientY);
            }
        }, { passive: true });

        // Pointer events для настільних ПК / миші / тачпаду
        let isPointerDown = false;
        calendarCard.addEventListener('pointerdown', (e) => {
            isPointerDown = true;
            handleStart(e.clientX, e.clientY);
        });

        calendarCard.addEventListener('pointerup', (e) => {
            if (isPointerDown) {
                isPointerDown = false;
                handleEnd(e.clientX, e.clientY);
            }
        });
    }

    document.getElementById('cal-prev')?.addEventListener('click', () => {
        const grid = document.getElementById('calendar-days');
        if (grid) grid.style.animation = 'slideRight 0.2s ease-out';
        currentCalDate.setMonth(currentCalDate.getMonth() - 1);
        setTimeout(() => {
            renderCalendar();
            if (grid) grid.style.animation = '';
        }, 100);
    });

    document.getElementById('cal-next')?.addEventListener('click', () => {
        const grid = document.getElementById('calendar-days');
        if (grid) grid.style.animation = 'slideLeft 0.2s ease-out';
        currentCalDate.setMonth(currentCalDate.getMonth() + 1);
        setTimeout(() => {
            renderCalendar();
            if (grid) grid.style.animation = '';
        }, 100);
    });


    function escapeHtml(text) {

        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    loadTasks();
});
