/**
 * Notification System
 * Handles logs, progress bars, and status labels.
 * Extracted from logic.js to decouple UI feedback logic.
 */

(function () {
    const ui = {
        get progressLabel() { return document.getElementById('progressLabel'); },
        get logContainer() { return document.getElementById('logContainer'); },
        get logContent() { return document.getElementById('logContent'); },
        get runBtn() { return document.getElementById('runBtn'); }
    };

    // Global exports for compatibility
    window.showProgress = function (label = 'Executing...') {
        if (ui.progressLabel) ui.progressLabel.textContent = label;
        updateProgress(0);
        if (ui.logContainer) {
            ui.logContainer.style.display = 'block';
            if (ui.logContent) ui.logContent.innerHTML = '';
        }
    };

    window.hideProgress = function () {
        // Progress is now on button, nothing to hide physically except resetting button style
        updateProgress(100);
    };

    window.updateProgress = function (percent, label) {
        if (label && ui.progressLabel) ui.progressLabel.textContent = label;

        // Use runBtn background as a progress bar
        if (ui.runBtn) {
            if (percent > 0 && percent < 100) {
                ui.runBtn.style.background = `linear-gradient(to right, var(--bg-active) ${percent}%, var(--bg-secondary) ${percent}%)`;
            } else {
                ui.runBtn.style.background = '';
                // Ensure text transparency is also handled if used
                ui.runBtn.style.backgroundImage = '';
            }
        }
    };

    window.addLog = function (message, type = 'info') {
        if (!ui.logContent) return;

        const time = new Date().toLocaleTimeString('en-US', { hour12: false });
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        entry.innerHTML = `
            <span class="log-time">[${time}]</span>
            <span class="log-message">${message}</span>
        `;
        ui.logContent.appendChild(entry);
        ui.logContent.scrollTop = ui.logContent.scrollHeight;
    };

    // [UI] Global Toast Notification (Bubble)
    window.showToast = function (message, type = 'info', duration = 3000) {
        const toastId = 'comfypanel-global-toast';
        let toast = document.getElementById(toastId);
        if (toast) toast.remove(); // Remove existing to prevent stacking overlap

        toast = document.createElement('div');
        toast.id = toastId;
        toast.className = `comfypanel-toast toast-${type}`;
        toast.textContent = message;

        const container = document.querySelector('.comfypanel-wrapper') || document.querySelector('#app') || document.body;
        container.appendChild(toast);

        // Slide and fade in (Class toggle)
        requestAnimationFrame(() => {
            requestAnimationFrame(() => { 
                toast.classList.add('toast-visible');
            });
        });

        // Fade out and remove
        setTimeout(() => {
            toast.classList.remove('toast-visible');
            setTimeout(() => toast.remove(), 300); // Wait for CSS transition
        }, duration);
    };

})();
