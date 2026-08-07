document.addEventListener('DOMContentLoaded', () => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
    }

    // --- Theme Engine Logic ---
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    
    function getPreferredTheme() {
        const savedTheme = localStorage.getItem('app_theme');
        if (savedTheme === 'light' || savedTheme === 'dark') {
            return savedTheme;
        }
        if (tg?.colorScheme === 'light' || tg?.colorScheme === 'dark') {
            return tg.colorScheme;
        }
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
            return 'light';
        }
        return 'dark';
    }

    function applyTheme(theme, save = false) {
        document.documentElement.setAttribute('data-theme', theme);
        if (themeToggleBtn) {
            themeToggleBtn.textContent = theme === 'light' ? '☀️' : '🌙';
            themeToggleBtn.setAttribute('title', theme === 'light' ? 'Світла тема' : 'Темна тема');
        }
        if (save) {
            localStorage.setItem('app_theme', theme);
        }
    }

    let currentTheme = getPreferredTheme();
    applyTheme(currentTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            currentTheme = currentTheme === 'light' ? 'dark' : 'light';
            applyTheme(currentTheme, true);
            showToast(currentTheme === 'light' ? '☀️ Увімкнено світлу тему' : '🌙 Увімкнено темну тему');
        });
    }

    if (tg) {
        tg.onEvent('themeChanged', () => {
            if (!localStorage.getItem('app_theme') && tg.colorScheme) {
                currentTheme = tg.colorScheme;
                applyTheme(currentTheme);
            }
        });
    }
    // --------------------------

    const initData = tg?.initData || '';
    
    let tasks = [];
    let currentFilter = 'today';
    let currentCalDate = new Date();
    let selectedSnoozeTaskId = null;

    function getLocalDateISO(d = new Date()) {
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    function getPresetDate(type) {
        const d = new Date();
        if (type === 'tomorrow') {
            d.setDate(d.getDate() + 1);
        } else if (type === 'in3days') {
            d.setDate(d.getDate() + 3);
        }
        return getLocalDateISO(d);
    }

    // Стан обраних дат, часів та інтервалу для створення
    let selectedDates = [getLocalDateISO()];
    let activeDateIndex = 0;
    let selectedTimes = ['09:00'];
    let activeTimeIndex = 0;
    let selectedInterval = 0;

    // Стан для редагування
    let editSelectedDates = [];
    let editActiveDateIndex = 0;
    let editSelectedTimes = [];
    let editActiveTimeIndex = 0;
    let editSelectedInterval = 0;

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
            } else if (targetTab === 'notifications') {
                loadNotifications();
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
            
            selectedTimes = [defaultTime];
            activeTimeIndex = 0;
            if (timePicker) timePicker.value = defaultTime;
            
            const todayStr = getLocalDateISO(now);
            selectedDates = [todayStr];
            activeDateIndex = 0;
            if (datePicker) datePicker.value = todayStr;

            renderTimeTags();
            renderDateTags();
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

    // Зміна значення у Time Picker (редагує ТІЛЬКИ активний слот, нові слоти НЕ створюються!)
    if (timePicker) {
        ['input', 'change'].forEach(evt => {
            timePicker.addEventListener(evt, (e) => {
                const val = e.target.value;
                if (!val) return;

                const existingIdx = selectedTimes.indexOf(val);
                if (existingIdx !== -1 && existingIdx !== activeTimeIndex) {
                    showToast('⚠️ Цей час вже додано у списку!');
                    if (timePicker) timePicker.value = selectedTimes[activeTimeIndex] || '09:00';
                    return;
                }

                if (activeTimeIndex >= 0 && activeTimeIndex < selectedTimes.length) {
                    selectedTimes[activeTimeIndex] = val;
                } else {
                    selectedTimes[0] = val;
                    activeTimeIndex = 0;
                }

                renderTimeTags();
            });
        });
    }

    if (datePicker) {
        ['input', 'change'].forEach(evt => {
            datePicker.addEventListener(evt, (e) => {
                const val = e.target.value;
                if (!val) return;

                const existingIdx = selectedDates.indexOf(val);
                if (existingIdx !== -1 && existingIdx !== activeDateIndex) {
                    showToast('⚠️ Цю дату вже додано у списку!');
                    if (datePicker) datePicker.value = selectedDates[activeDateIndex] || getLocalDateISO();
                    return;
                }

                if (activeDateIndex >= 0 && activeDateIndex < selectedDates.length) {
                    selectedDates[activeDateIndex] = val;
                } else {
                    selectedDates[0] = val;
                    activeDateIndex = 0;
                }

                renderDateTags();
            });
        });
    }


    // Рендеринг тегів дат (Створення)
    function renderDateTags() {
        const container = document.getElementById('selected-dates-container');
        if (!container) return;
        container.innerHTML = '';

        if (selectedDates.length === 0) {
            const todayStr = getLocalDateISO();
            selectedDates = [todayStr];
            activeDateIndex = 0;
            if (datePicker) datePicker.value = todayStr;
        }

        if (activeDateIndex < 0 || activeDateIndex >= selectedDates.length) {
            activeDateIndex = Math.max(0, selectedDates.length - 1);
        }

        selectedDates.forEach((d, idx) => {
            const tag = document.createElement('span');
            const isActive = (idx === activeDateIndex);
            tag.className = `tag-item ${isActive ? 'active-tag' : ''}`;
            tag.innerHTML = `📅 ${d} <button type="button" class="remove-date-tag" data-index="${idx}" aria-label="Видалити дату ${d}">❌</button>`;

            tag.addEventListener('click', (e) => {
                if (e.target.classList.contains('remove-date-tag')) return;
                activeDateIndex = idx;
                if (datePicker) datePicker.value = selectedDates[idx];
                renderDateTags();
            });

            container.appendChild(tag);
        });

        // Підсвічуємо активні пресети дати
        const todayStr = getPresetDate('today');
        const tomStr = getPresetDate('tomorrow');
        const d3Str = getPresetDate('in3days');

        const presetTodayEl = document.getElementById('preset-today');
        if (presetTodayEl) {
            const isAct = selectedDates.includes(todayStr);
            presetTodayEl.classList.toggle('active', isAct);
            presetTodayEl.setAttribute('aria-pressed', isAct ? 'true' : 'false');
        }
        const presetTomEl = document.getElementById('preset-tomorrow');
        if (presetTomEl) {
            const isAct = selectedDates.includes(tomStr);
            presetTomEl.classList.toggle('active', isAct);
            presetTomEl.setAttribute('aria-pressed', isAct ? 'true' : 'false');
        }
        const presetD3El = document.getElementById('preset-in3days');
        if (presetD3El) {
            const isAct = selectedDates.includes(d3Str);
            presetD3El.classList.toggle('active', isAct);
            presetD3El.setAttribute('aria-pressed', isAct ? 'true' : 'false');
        }

        container.querySelectorAll('.remove-date-tag').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idxToRemove = parseInt(e.currentTarget.dataset.index);
                selectedDates.splice(idxToRemove, 1);

                if (selectedDates.length === 0) {
                    const fallback = getLocalDateISO();
                    selectedDates = [fallback];
                    activeDateIndex = 0;
                    if (datePicker) datePicker.value = fallback;
                } else {
                    activeDateIndex = Math.min(activeDateIndex, selectedDates.length - 1);
                    if (datePicker) datePicker.value = selectedDates[activeDateIndex];
                }
                renderDateTags();
            });
        });
    }

    const addDateBtn = document.getElementById('add-date-btn');
    if (addDateBtn) {
        addDateBtn.addEventListener('click', () => {
            const curVal = datePicker ? datePicker.value : getLocalDateISO();
            
            let nextDate = curVal;
            if (selectedDates.includes(curVal)) {
                let d = new Date(curVal);
                let guard = 0;
                while (selectedDates.includes(nextDate) && guard < 365) {
                    d.setDate(d.getDate() + 1);
                    nextDate = getLocalDateISO(d);
                    guard++;
                }
            }

            if (selectedDates.includes(nextDate)) {
                showToast('⚠️ Усі найближчі дати вже додано у списку!');
                return;
            }

            selectedDates.push(nextDate);
            activeDateIndex = selectedDates.length - 1;
            if (datePicker) datePicker.value = nextDate;
            renderDateTags();
        });
    }

    // Рендеринг тегів часів (Створення)
    function renderTimeTags() {
        const container = document.getElementById('selected-times-container');
        if (!container) return;
        container.innerHTML = '';

        if (activeTimeIndex < 0 || activeTimeIndex >= selectedTimes.length) {
            activeTimeIndex = Math.max(0, selectedTimes.length - 1);
        }

        selectedTimes.forEach((t, idx) => {
            const tag = document.createElement('span');
            const isActive = (idx === activeTimeIndex);
            tag.className = `tag-item ${isActive ? 'active-tag' : ''}`;
            tag.innerHTML = `🕒 ${t} <button type="button" class="remove-tag" data-index="${idx}" aria-label="Видалити час ${t}">❌</button>`;

            // Тап на тіло тегу підключає колесо часу до нього
            tag.addEventListener('click', (e) => {
                if (e.target.classList.contains('remove-tag')) return;
                activeTimeIndex = idx;
                if (timePicker) timePicker.value = selectedTimes[idx];
                renderTimeTags();
            });

            container.appendChild(tag);
        });

        // Підсвічуємо активні пресети
        document.querySelectorAll('.time-preset-chip').forEach(chip => {
            const t = chip.dataset.time;
            const isAct = selectedTimes.includes(t);
            chip.classList.toggle('active', isAct);
            chip.setAttribute('aria-pressed', isAct ? 'true' : 'false');
        });

        container.querySelectorAll('.remove-tag').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idxToRemove = parseInt(e.currentTarget.dataset.index);
                selectedTimes.splice(idxToRemove, 1);

                if (selectedTimes.length === 0) {
                    const fallback = '09:00';
                    selectedTimes = [fallback];
                    activeTimeIndex = 0;
                    if (timePicker) timePicker.value = fallback;
                } else {
                    activeTimeIndex = Math.min(activeTimeIndex, selectedTimes.length - 1);
                    if (timePicker) timePicker.value = selectedTimes[activeTimeIndex];
                }
                renderTimeTags();
            });
        });
    }

    // Кнопка "➕ Додати час" ЯВНО створює новий слот
    const addTimeBtn = document.getElementById('add-time-btn');
    if (addTimeBtn) {
        addTimeBtn.addEventListener('click', () => {
            const curVal = timePicker ? timePicker.value : '09:00';
            
            let nextTime = curVal;
            if (selectedTimes.includes(curVal)) {
                const parts = curVal.split(':');
                let h = (parseInt(parts[0], 10) + 1) % 24;
                const m = parts[1] || '00';
                nextTime = `${String(h).padStart(2, '0')}:${m}`;
                
                let guard = 0;
                while (selectedTimes.includes(nextTime) && guard < 24) {
                    h = (h + 1) % 24;
                    nextTime = `${String(h).padStart(2, '0')}:${m}`;
                    guard++;
                }
            }

            if (selectedTimes.includes(nextTime)) {
                showToast('⚠️ Усі доступні часові слоти вже додано!');
                return;
            }

            selectedTimes.push(nextTime);
            activeTimeIndex = selectedTimes.length - 1;
            if (timePicker) timePicker.value = nextTime;
            renderTimeTags();
        });
    }

    document.querySelectorAll('.time-preset-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            const t = e.currentTarget.dataset.time;
            if (!t) return;

            if (selectedTimes.includes(t)) {
                if (selectedTimes.length > 1) {
                    const idx = selectedTimes.indexOf(t);
                    selectedTimes.splice(idx, 1);
                    activeTimeIndex = Math.min(activeTimeIndex, selectedTimes.length - 1);
                    if (timePicker) timePicker.value = selectedTimes[activeTimeIndex];
                }
            } else {
                if (selectedTimes.length === 1 && activeTimeIndex === 0) {
                    selectedTimes[0] = t;
                } else {
                    selectedTimes.push(t);
                    activeTimeIndex = selectedTimes.length - 1;
                }
                if (timePicker) timePicker.value = t;
            }
            renderTimeTags();
        });
    });


    // Швидкі пресети дати (Створення - логіка як у часів)
    function applyDatePreset(presetDate) {
        if (selectedDates.includes(presetDate)) {
            if (selectedDates.length > 1) {
                const idx = selectedDates.indexOf(presetDate);
                selectedDates.splice(idx, 1);
                activeDateIndex = Math.min(activeDateIndex, selectedDates.length - 1);
                if (datePicker) datePicker.value = selectedDates[activeDateIndex];
            }
        } else {
            if (selectedDates.length === 1 && activeDateIndex === 0) {
                selectedDates[0] = presetDate;
            } else {
                selectedDates.push(presetDate);
                activeDateIndex = selectedDates.length - 1;
            }
            if (datePicker) datePicker.value = presetDate;
        }
        renderDateTags();
    }

    document.getElementById('preset-today')?.addEventListener('click', () => {
        applyDatePreset(getPresetDate('today'));
    });

    document.getElementById('preset-tomorrow')?.addEventListener('click', () => {
        applyDatePreset(getPresetDate('tomorrow'));
    });

    document.getElementById('preset-in3days')?.addEventListener('click', () => {
        applyDatePreset(getPresetDate('in3days'));
    });

    // Інпут та швидкі чіпи інтервалу (Створення)
    const intervalInput = document.getElementById('task-interval-input');
    const intervalChips = document.querySelectorAll('.interval-chip:not(.edit-interval-chip)');

    function updateCreationIntervalChips(val) {
        selectedInterval = Math.max(0, parseInt(val) || 0);
        intervalChips.forEach(chip => {
            const mins = parseInt(chip.dataset.minutes) || 0;
            chip.classList.toggle('active', mins === selectedInterval);
        });
    }

    if (intervalInput) {
        intervalInput.addEventListener('input', (e) => {
            updateCreationIntervalChips(e.target.value);
        });
    }

    intervalChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            const mins = parseInt(e.currentTarget.dataset.minutes) || 0;
            if (intervalInput) intervalInput.value = mins > 0 ? mins : '';
            updateCreationIntervalChips(mins);
        });
    });
    // Завантаження завдань з API
    async function loadTasks() {
        try {
            const data = await apiRequest('/api/tasks');
            tasks = data.tasks || [];

            // Оновити лічильник та прогрес
            const countEl = document.getElementById('stats-subtitle') || document.getElementById('tasks-count');
            if (countEl) countEl.textContent = `${tasks.length} активних нагадувань`;

            const progressEl = document.getElementById('progress-percent');
            if (progressEl) progressEl.textContent = `${data.progress_percent || 0}%`;

            const progressBar = document.getElementById('progress-bar-fill');
            if (progressBar) progressBar.style.width = `${data.progress_percent || 0}%`;

            renderTaskList();
            loadNotifications();
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
        const todayDate = new Date();

        const filtered = tasks.filter(t => {
            if (currentFilter === 'today') {
                return isTaskOnDate(t, todayDate, todayIndex);
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
                    <button class="btn-small btn-secondary edit-btn" data-id="${task.task_id}">✏️ Редагувати</button>
                    <button class="btn-small btn-primary snooze-btn" data-id="${task.task_id}">⏸ Відкласти</button>
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

        const editDatesGroup = document.getElementById('edit-dates-selector-group');
        const editDaysGroup = document.getElementById('edit-days-group');

        if (task.is_one_time) {
            if (editDatesGroup) editDatesGroup.classList.remove('hidden');
            if (editDaysGroup) editDaysGroup.classList.add('hidden');

            if (task.one_time_date) {
                editSelectedDates = task.one_time_date.split(',').map(s => s.trim()).filter(Boolean);
            } else {
                editSelectedDates = [getLocalDateISO()];
            }
            editActiveDateIndex = 0;
            const editDatePicker = document.getElementById('edit-task-date-picker');
            if (editDatePicker) editDatePicker.value = editSelectedDates[0] || getLocalDateISO();
            renderEditDateTags();
        } else {
            if (editDatesGroup) editDatesGroup.classList.add('hidden');
            if (editDaysGroup) editDaysGroup.classList.remove('hidden');
        }

        editSelectedTimes = [...task.times];
        editActiveTimeIndex = 0;
        const editTimePicker = document.getElementById('edit-task-time-picker');
        if (editTimePicker) editTimePicker.value = editSelectedTimes[0] || '09:00';

        renderEditTimeTags();

        editSelectedInterval = task.interval_minutes || 0;
        const editIntervalInput = document.getElementById('edit-task-interval-input');
        if (editIntervalInput) editIntervalInput.value = editSelectedInterval > 0 ? editSelectedInterval : '';
        updateEditIntervalChips(editSelectedInterval);

        document.querySelectorAll('.edit-day-chip').forEach(chip => {
            const dayVal = parseInt(chip.dataset.day);
            chip.classList.toggle('active', task.days.includes(dayVal));
        });

        if (editModal) editModal.classList.remove('hidden');
    }

    function renderEditDateTags() {
        const container = document.getElementById('edit-selected-dates-container');
        if (!container) return;
        container.innerHTML = '';

        const editDatePicker = document.getElementById('edit-task-date-picker');

        if (editSelectedDates.length === 0) {
            const todayStr = getLocalDateISO();
            editSelectedDates = [todayStr];
            editActiveDateIndex = 0;
            if (editDatePicker) editDatePicker.value = todayStr;
        }

        if (editActiveDateIndex < 0 || editActiveDateIndex >= editSelectedDates.length) {
            editActiveDateIndex = Math.max(0, editSelectedDates.length - 1);
        }

        editSelectedDates.forEach((d, idx) => {
            const tag = document.createElement('span');
            const isActive = (idx === editActiveDateIndex);
            tag.className = `tag-item ${isActive ? 'active-tag' : ''}`;
            tag.innerHTML = `📅 ${d} <button type="button" class="edit-remove-date-tag" data-index="${idx}" aria-label="Видалити дату ${d}">❌</button>`;

            tag.addEventListener('click', (e) => {
                if (e.target.classList.contains('edit-remove-date-tag')) return;
                editActiveDateIndex = idx;
                if (editDatePicker) editDatePicker.value = editSelectedDates[idx];
                renderEditDateTags();
            });

            container.appendChild(tag);
        });

        // Підсвічуємо активні пресети дати в редагуванні
        const todayStr = getPresetDate('today');
        const tomStr = getPresetDate('tomorrow');
        const d3Str = getPresetDate('in3days');

        const editPresetTodayEl = document.getElementById('edit-preset-today');
        if (editPresetTodayEl) {
            const isAct = editSelectedDates.includes(todayStr);
            editPresetTodayEl.classList.toggle('active', isAct);
            editPresetTodayEl.setAttribute('aria-pressed', isAct ? 'true' : 'false');
        }
        const editPresetTomEl = document.getElementById('edit-preset-tomorrow');
        if (editPresetTomEl) {
            const isAct = editSelectedDates.includes(tomStr);
            editPresetTomEl.classList.toggle('active', isAct);
            editPresetTomEl.setAttribute('aria-pressed', isAct ? 'true' : 'false');
        }
        const editPresetD3El = document.getElementById('edit-preset-in3days');
        if (editPresetD3El) {
            const isAct = editSelectedDates.includes(d3Str);
            editPresetD3El.classList.toggle('active', isAct);
            editPresetD3El.setAttribute('aria-pressed', isAct ? 'true' : 'false');
        }

        container.querySelectorAll('.edit-remove-date-tag').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idxToRemove = parseInt(e.currentTarget.dataset.index);
                editSelectedDates.splice(idxToRemove, 1);

                if (editSelectedDates.length === 0) {
                    const fallback = getLocalDateISO();
                    editSelectedDates = [fallback];
                    editActiveDateIndex = 0;
                    if (editDatePicker) editDatePicker.value = fallback;
                } else {
                    editActiveDateIndex = Math.min(editActiveDateIndex, editSelectedDates.length - 1);
                    if (editDatePicker) editDatePicker.value = editSelectedDates[editActiveDateIndex];
                }
                renderEditDateTags();
            });
        });
    }

    const editAddDateBtn = document.getElementById('edit-add-date-btn');
    if (editAddDateBtn) {
        editAddDateBtn.addEventListener('click', () => {
            const editDatePicker = document.getElementById('edit-task-date-picker');
            const curVal = editDatePicker ? editDatePicker.value : getLocalDateISO();
            
            let nextDate = curVal;
            if (editSelectedDates.includes(curVal)) {
                let d = new Date(curVal);
                let guard = 0;
                while (editSelectedDates.includes(nextDate) && guard < 365) {
                    d.setDate(d.getDate() + 1);
                    nextDate = getLocalDateISO(d);
                    guard++;
                }
            }

            if (editSelectedDates.includes(nextDate)) {
                showToast('⚠️ Усі найближчі дати вже додано у списку!');
                return;
            }

            editSelectedDates.push(nextDate);
            editActiveDateIndex = editSelectedDates.length - 1;
            if (editDatePicker) editDatePicker.value = nextDate;
            renderEditDateTags();
        });
    }

    function applyEditDatePreset(presetDate) {
        const editDatePicker = document.getElementById('edit-task-date-picker');
        if (editSelectedDates.includes(presetDate)) {
            if (editSelectedDates.length > 1) {
                const idx = editSelectedDates.indexOf(presetDate);
                editSelectedDates.splice(idx, 1);
                editActiveDateIndex = Math.min(editActiveDateIndex, editSelectedDates.length - 1);
                if (editDatePicker) editDatePicker.value = editSelectedDates[editActiveDateIndex];
            }
        } else {
            if (editSelectedDates.length === 1 && editActiveDateIndex === 0) {
                editSelectedDates[0] = presetDate;
            } else {
                editSelectedDates.push(presetDate);
                editActiveDateIndex = editSelectedDates.length - 1;
            }
            if (editDatePicker) editDatePicker.value = presetDate;
        }
        renderEditDateTags();
    }

    document.getElementById('edit-preset-today')?.addEventListener('click', () => {
        applyEditDatePreset(getPresetDate('today'));
    });

    document.getElementById('edit-preset-tomorrow')?.addEventListener('click', () => {
        applyEditDatePreset(getPresetDate('tomorrow'));
    });

    document.getElementById('edit-preset-in3days')?.addEventListener('click', () => {
        applyEditDatePreset(getPresetDate('in3days'));
    });

    const editDatePickerEl = document.getElementById('edit-task-date-picker');
    if (editDatePickerEl) {
        ['input', 'change'].forEach(evt => {
            editDatePickerEl.addEventListener(evt, (e) => {
                const val = e.target.value;
                if (!val) return;

                const existingIdx = editSelectedDates.indexOf(val);
                if (existingIdx !== -1 && existingIdx !== editActiveDateIndex) {
                    showToast('⚠️ Цю дату вже додано у списку!');
                    if (editDatePickerEl) editDatePickerEl.value = editSelectedDates[editActiveDateIndex] || getLocalDateISO();
                    return;
                }

                if (editActiveDateIndex >= 0 && editActiveDateIndex < editSelectedDates.length) {
                    editSelectedDates[editActiveDateIndex] = val;
                } else {
                    editSelectedDates[0] = val;
                    editActiveDateIndex = 0;
                }

                renderEditDateTags();
            });
        });
    }

    function renderEditTimeTags() {
        const container = document.getElementById('edit-selected-times-container');
        if (!container) return;
        container.innerHTML = '';

        if (editActiveTimeIndex < 0 || editActiveTimeIndex >= editSelectedTimes.length) {
            editActiveTimeIndex = Math.max(0, editSelectedTimes.length - 1);
        }

        editSelectedTimes.forEach((t, idx) => {
            const tag = document.createElement('span');
            const isActive = (idx === editActiveTimeIndex);
            tag.className = `tag-item ${isActive ? 'active-tag' : ''}`;
            tag.innerHTML = `🕒 ${t} <button type="button" class="edit-remove-tag" data-index="${idx}" aria-label="Видалити час ${t}">❌</button>`;

            tag.addEventListener('click', (e) => {
                if (e.target.classList.contains('edit-remove-tag')) return;
                editActiveTimeIndex = idx;
                const picker = document.getElementById('edit-task-time-picker');
                if (picker) picker.value = editSelectedTimes[idx];
                renderEditTimeTags();
            });

            container.appendChild(tag);
        });

        // Підсвічуємо активні чіпи в модалці редагування
        document.querySelectorAll('.edit-time-preset-chip').forEach(chip => {
            const t = chip.dataset.time;
            chip.classList.toggle('active', editSelectedTimes.includes(t));
        });

        container.querySelectorAll('.edit-remove-tag').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idxToRemove = parseInt(e.currentTarget.dataset.index);
                editSelectedTimes.splice(idxToRemove, 1);

                if (editSelectedTimes.length === 0) {
                    const fallback = '09:00';
                    editSelectedTimes = [fallback];
                    editActiveTimeIndex = 0;
                    const picker = document.getElementById('edit-task-time-picker');
                    if (picker) picker.value = fallback;
                } else {
                    editActiveTimeIndex = Math.min(editActiveTimeIndex, editSelectedTimes.length - 1);
                    const picker = document.getElementById('edit-task-time-picker');
                    if (picker) picker.value = editSelectedTimes[editActiveTimeIndex];
                }
                renderEditTimeTags();
            });
        });
    }

    const editAddTimeBtn = document.getElementById('edit-add-time-btn');
    if (editAddTimeBtn) {
        editAddTimeBtn.addEventListener('click', () => {
            const picker = document.getElementById('edit-task-time-picker');
            const curVal = picker ? picker.value : '09:00';
            
            let nextTime = curVal;
            if (editSelectedTimes.includes(curVal)) {
                const parts = curVal.split(':');
                let h = (parseInt(parts[0], 10) + 1) % 24;
                const m = parts[1] || '00';
                nextTime = `${String(h).padStart(2, '0')}:${m}`;
                
                let guard = 0;
                while (editSelectedTimes.includes(nextTime) && guard < 24) {
                    h = (h + 1) % 24;
                    nextTime = `${String(h).padStart(2, '0')}:${m}`;
                    guard++;
                }
            }

            if (editSelectedTimes.includes(nextTime)) {
                showToast('⚠️ Усі доступні часові слоти вже додано!');
                return;
            }

            editSelectedTimes.push(nextTime);
            editActiveTimeIndex = editSelectedTimes.length - 1;
            if (picker) picker.value = nextTime;
            renderEditTimeTags();
        });
    }

    const editTimePicker = document.getElementById('edit-task-time-picker');
    if (editTimePicker) {
        ['input', 'change'].forEach(evt => {
            editTimePicker.addEventListener(evt, (e) => {
                const val = e.target.value;
                if (!val) return;

                if (editActiveTimeIndex >= 0 && editActiveTimeIndex < editSelectedTimes.length) {
                    editSelectedTimes[editActiveTimeIndex] = val;
                } else {
                    editSelectedTimes[0] = val;
                    editActiveTimeIndex = 0;
                }

                renderEditTimeTags();
            });
        });
    }


    document.querySelectorAll('.edit-time-preset-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            const t = e.currentTarget.dataset.time;
            if (!t) return;

            if (editSelectedTimes.includes(t)) {
                if (editSelectedTimes.length > 1) {
                    const idx = editSelectedTimes.indexOf(t);
                    editSelectedTimes.splice(idx, 1);
                    editActiveTimeIndex = Math.min(editActiveTimeIndex, editSelectedTimes.length - 1);
                    if (editTimePicker) editTimePicker.value = editSelectedTimes[editActiveTimeIndex];
                }
            } else {
                if (editSelectedTimes.length === 1 && editActiveTimeIndex === 0) {
                    editSelectedTimes[0] = t;
                } else {
                    editSelectedTimes.push(t);
                    editActiveTimeIndex = editSelectedTimes.length - 1;
                }
                if (editTimePicker) editTimePicker.value = t;
            }
            renderEditTimeTags();
        });
    });


    const editIntervalInput = document.getElementById('edit-task-interval-input');
    const editIntervalChips = document.querySelectorAll('.edit-interval-chip');

    function updateEditIntervalChips(val) {
        editSelectedInterval = Math.max(0, parseInt(val) || 0);
        editIntervalChips.forEach(chip => {
            const mins = parseInt(chip.dataset.minutes) || 0;
            chip.classList.toggle('active', mins === editSelectedInterval);
        });
    }

    if (editIntervalInput) {
        editIntervalInput.addEventListener('input', (e) => {
            updateEditIntervalChips(e.target.value);
        });
    }

    editIntervalChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            const mins = parseInt(e.currentTarget.dataset.minutes) || 0;
            if (editIntervalInput) editIntervalInput.value = mins > 0 ? mins : '';
            updateEditIntervalChips(mins);
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

            const editTask = tasks.find(t => t.task_id === parseInt(taskId));
            let one_time_date = undefined;
            if (editTask && editTask.is_one_time) {
                one_time_date = editSelectedDates.length > 0 ? editSelectedDates.join(', ') : (document.getElementById('edit-task-date-picker')?.value || getLocalDateISO());
            }

            try {
                await apiRequest(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    body: JSON.stringify({
                        description,
                        times,
                        interval_minutes,
                        one_time_date,
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
                one_time_date = selectedDates.length > 0 ? selectedDates.join(', ') : (datePicker ? datePicker.value : getLocalDateISO());
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
                
                selectedDates = [getLocalDateISO()];
                activeDateIndex = 0;
                if (datePicker) datePicker.value = getLocalDateISO();
                renderDateTags();

                const defaultTime = '09:00';
                selectedTimes = [defaultTime];
                activeTimeIndex = 0;
                if (timePicker) timePicker.value = defaultTime;
                renderTimeTags();
                
                if (createModal) createModal.classList.add('hidden');
                loadTasks();
            } catch (err) {
                // Handled
            }
        });
    }

    function isTaskOnDate(t, cellDate, dayOfWeek) {
        if (!t) return false;

        const isOneTime = Boolean(t.is_one_time && t.is_one_time !== 'false' && t.is_one_time !== '0');

        if (!isOneTime) {
            if (!t.days || !Array.isArray(t.days) || t.days.length === 0) return true;
            return t.days.some(d => Number(d) === Number(dayOfWeek));
        }

        if (isOneTime && t.one_time_date) {
            const cellISO = getLocalDateISO(cellDate);
            const dates = String(t.one_time_date).split(',').map(d => d.trim());
            return dates.some(d => {
                if (!d) return false;
                const dClean = d.substring(0, 10);
                if (dClean === cellISO) return true;
                if (dClean.includes('.')) {
                    const parts = dClean.split('.');
                    if (parts.length === 3) {
                        const formatted = `${parts[2]}-${parts[1].padStart(2, '0')}-${parts[0].padStart(2, '0')}`;
                        return formatted === cellISO;
                    }
                }
                if (dClean.includes('-')) {
                    const parts = dClean.split('-');
                    if (parts.length === 3) {
                        const formatted = `${parts[0]}-${parts[1].padStart(2, '0')}-${parts[2].padStart(2, '0')}`;
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

    // --- Notifications Logic ---
    let notifications = [];
    let currentNotifFilter = 'today';

    async function loadNotifications() {
        try {
            const data = await apiRequest('/api/notifications');
            if (data && data.status === 'ok') {
                notifications = data.notifications || [];
                updateUnreadBadge(data.unread_count || 0);
                renderNotificationsList();
            }
        } catch (err) {
            console.error('Error loading notifications:', err);
        }
    }

    function updateUnreadBadge(count) {
        const badgeEl = document.getElementById('unread-badge');
        if (!badgeEl) return;
        if (count > 0) {
            badgeEl.textContent = count > 99 ? '99+' : count;
            badgeEl.classList.remove('hidden');
        } else {
            badgeEl.classList.add('hidden');
        }
    }

    function renderNotificationsList() {
        const container = document.getElementById('notifications-container');
        if (!container) return;

        let filtered = [...notifications];
        const todayStr = getLocalDateISO(new Date());

        if (currentNotifFilter === 'unread') {
            filtered = filtered.filter(n => !n.is_read);
        } else if (currentNotifFilter === 'today') {
            filtered = filtered.filter(n => n.created_at && n.created_at.startsWith(todayStr));
        }

        if (filtered.length === 0) {
            container.innerHTML = `
                <div class="loading-spinner">
                    🔔 ${currentNotifFilter === 'unread' ? 'Немає непрочитаних сповіщень' : 'Історія сповіщень порожня'}
                </div>
            `;
            return;
        }

        container.innerHTML = filtered.map(notif => {
            const isCompleted = notif.is_completed || false;
            const timeStr = notif.created_at ? notif.created_at.replace('T', ' ').substring(0, 16) : '';

            let actionsHtml = '';
            if (isCompleted) {
                actionsHtml = `<div class="notif-status-done">✅ Виконано</div>`;
            } else {
                actionsHtml = `
                    <button class="btn-small btn-success notif-done-btn" data-id="${notif.id}" data-task-id="${notif.task_id}" data-inst-id="${notif.reminder_instance_id}">✅ Готово</button>
                    <button class="btn-small btn-primary notif-snooze-btn" data-task-id="${notif.task_id}">⏸ Відкласти</button>
                `;
            }

            return `
                <div class="notification-card ${isCompleted ? 'completed-card' : ''}" data-id="${notif.id}">
                    <div class="notif-header">
                        <div class="notif-title">
                            ${isCompleted ? '✅' : '🔔'} ${escapeHtml(notif.title || 'Сповіщення')}
                        </div>
                        <span class="notif-time">${timeStr}</span>
                    </div>
                    <div class="notif-body">${escapeHtml(notif.message || '')}</div>
                    <div class="notif-card-actions">
                        ${actionsHtml}
                    </div>
                </div>
            `;
        }).join('');

        container.querySelectorAll('.notif-done-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const notifId = btn.dataset.id;
                const taskId = btn.dataset.taskId;
                const instId = btn.dataset.instId;
                try {
                    await apiRequest(`/api/tasks/${taskId}/complete`, {
                        method: 'POST',
                        body: JSON.stringify({ reminder_instance_id: instId })
                    });
                    if (notifId) {
                        await apiRequest(`/api/notifications/${notifId}/read`, { method: 'POST' }).catch(() => {});
                    }
                    showToast('✅ Нагадування виконано!');
                    loadTasks();
                    loadNotifications();
                } catch (err) {
                    console.error('Error completing task from notification:', err);
                }
            });
        });

        container.querySelectorAll('.notif-snooze-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                selectedSnoozeTaskId = parseInt(btn.dataset.taskId);
                const titleEl = document.getElementById('snooze-modal-title');
                if (titleEl) titleEl.textContent = `⏸ Відкласти завдання #${selectedSnoozeTaskId}`;
                if (snoozeModal) snoozeModal.classList.remove('hidden');
            });
        });
    }

    // Filter chips for Notifications
    const notifFilterChips = document.querySelectorAll('.notif-filter-chip');
    notifFilterChips.forEach(chip => {
        chip.addEventListener('click', () => {
            notifFilterChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentNotifFilter = chip.dataset.filter;
            renderNotificationsList();
        });
    });

    const clearNotifsBtn = document.getElementById('clear-notifs-btn');
    if (clearNotifsBtn) {
        clearNotifsBtn.addEventListener('click', async () => {
            if (!confirm('Ви дійсно бажаєте очистити історію сповіщень?')) return;
            try {
                await apiRequest('/api/notifications/clear', { method: 'POST' });
                showToast('🗑 Історію сповіщень очищено');
                loadNotifications();
            } catch (err) {
                console.error('Error clearing notifications:', err);
            }
        });
    }

    renderTimeTags();
    renderDateTags();
    loadTasks();
    loadNotifications();
});
