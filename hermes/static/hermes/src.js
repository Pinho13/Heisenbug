document.addEventListener('DOMContentLoaded', function() {

    // ========== CURRENCIES DATABASE ==========
    const allCurrencies = [
        { symbol: 'EUR', name: 'Euro', icon: '€', color: 'from-[#3b82f6] to-[#2563eb]' },
        { symbol: 'USD', name: 'Dollar', icon: '$', color: 'from-[#22c55e] to-[#16a34a]' },
        { symbol: 'BTC', name: 'Bitcoin', icon: '₿', color: 'from-[#fb923c] to-[#ea580c]' },
        { symbol: 'ETH', name: 'Ethereum', icon: 'Ξ', color: 'from-[#a855f7] to-[#7c3aed]' },
    ];

    let selectedCurrencies = [];

    // ========== PERSISTENCE HELPERS ==========
    function saveToLocalStorage() {
        localStorage.setItem('hermes_selected_currencies', JSON.stringify(selectedCurrencies));
        const amountVal = document.getElementById('amountInput').value;
        if (amountVal) localStorage.setItem('hermes_investment_amount', amountVal);
    }

    function syncToBackend() {
        const amountVal = document.getElementById('amountInput').value || '0';
        fetch('/hermes/api/preferences/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                selected_currencies: selectedCurrencies,
                investment_amount: amountVal
            })
        }).catch(err => console.error('Error syncing preferences:', err));
    }

    function loadPreferences() {
        // Try localStorage first for instant display
        const cached = localStorage.getItem('hermes_selected_currencies');
        if (cached) {
            try {
                selectedCurrencies = JSON.parse(cached);
                updateCurrenciesDisplay();
            } catch (e) { /* ignore parse errors */ }
        }
        const cachedAmount = localStorage.getItem('hermes_investment_amount');
        if (cachedAmount) {
            const amountInput = document.getElementById('amountInput');
            if (amountInput) amountInput.value = cachedAmount;
        }

        // Then fetch from backend (source of truth)
        fetch('/hermes/api/preferences/')
            .then(r => r.json())
            .then(data => {
                if (data.selected_currencies && data.selected_currencies.length > 0) {
                    selectedCurrencies = data.selected_currencies;
                    updateCurrenciesDisplay();
                    localStorage.setItem('hermes_selected_currencies', JSON.stringify(selectedCurrencies));
                }
                if (data.investment_amount && data.investment_amount !== '0' && data.investment_amount !== '0.00') {
                    const amountInput = document.getElementById('amountInput');
                    if (amountInput) amountInput.value = data.investment_amount;
                    localStorage.setItem('hermes_investment_amount', data.investment_amount);
                }
            })
            .catch(err => console.error('Error loading preferences:', err));
    }

    // ========== CURRENCY SEARCH ==========
    const currencySearch = document.getElementById('currencySearch');
    const currencyDropdown = document.getElementById('currencyDropdown');
    const selectedCurrenciesContainer = document.getElementById('selectedCurrencies');

    // Show placeholder until preferences load
    selectedCurrenciesContainer.innerHTML = '<div class="w-full text-center text-[#64748b] text-sm">Loading...</div>';

    function showDropdown(query) {
        const results = allCurrencies.filter(currency =>
            currency.symbol.toLowerCase().includes(query) ||
            currency.name.toLowerCase().includes(query)
        );

        if (results.length === 0) {
            currencyDropdown.innerHTML = '<div class="p-3 text-sm text-[#64748b]">No currencies found</div>';
            currencyDropdown.classList.remove('hidden');
            return;
        }

        currencyDropdown.innerHTML = results.map(currency => `
        <div class="p-3 hover:bg-[#1a1a2e] cursor-pointer flex items-center gap-3 currency-result ${selectedCurrencies.includes(currency.symbol) ? 'opacity-50' : ''}"
             data-symbol="${currency.symbol}"
             data-name="${currency.name}"
             data-icon="${currency.icon}"
             data-color="${currency.color}">
            <div class="w-8 h-8 rounded-full bg-gradient-to-br ${currency.color} flex items-center justify-center text-lg font-bold">
                ${currency.icon}
            </div>
            <div class="flex-1">
                <div class="text-sm font-semibold">${currency.symbol}</div>
                <div class="text-xs text-[#94a3b8]">${currency.name}</div>
            </div>
            ${selectedCurrencies.includes(currency.symbol) ? '<span class="text-xs text-[#22c55e]">✓ Selected</span>' : ''}
        </div>
    `).join('');

        currencyDropdown.classList.remove('hidden');
    }

    currencySearch.addEventListener('focus', function() {
        showDropdown('');
    });

    currencySearch.addEventListener('input', function(e) {
        const query = e.target.value.toLowerCase().trim();
        showDropdown(query);
    });

    currencyDropdown.addEventListener('click', function(e) {
        const resultElement = e.target.closest('.currency-result');
        if (!resultElement) return;

        const symbol = resultElement.dataset.symbol;

        if (selectedCurrencies.includes(symbol)) return;
        if (selectedCurrencies.length >= 4) {
            alert('Maximum 4 currencies allowed');
            return;
        }

        selectedCurrencies.push(symbol);
        updateCurrenciesDisplay();
        saveToLocalStorage();
        syncToBackend();

        currencySearch.value = '';
        currencyDropdown.classList.add('hidden');
    });

    document.addEventListener('click', function(e) {
        if (!currencySearch.contains(e.target) && !currencyDropdown.contains(e.target)) {
            currencyDropdown.classList.add('hidden');
        }
    });

    function updateCurrenciesDisplay() {
        if (selectedCurrencies.length === 0) {
            selectedCurrenciesContainer.innerHTML = '<div class="w-full text-center text-[#64748b] text-sm">No currencies selected</div>';
            return;
        }

        selectedCurrenciesContainer.innerHTML = '';

        selectedCurrencies.forEach(symbol => {
            const currency = allCurrencies.find(c => c.symbol === symbol);
            if (!currency) return;

            const currencyItem = document.createElement('div');
            currencyItem.className = 'currency-item flex flex-col items-center gap-1';
            currencyItem.dataset.symbol = symbol;
            currencyItem.innerHTML = `
            <div class="w-14 h-14 rounded-full bg-gradient-to-br ${currency.color} flex items-center justify-center text-2xl font-bold shadow-lg cursor-pointer relative group">
                ${currency.icon}
                <button class="remove-currency absolute -top-1 -right-1 w-5 h-5 bg-[#ef4444] rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            <span class="text-xs text-[#94a3b8]">${symbol}</span>
        `;

            selectedCurrenciesContainer.appendChild(currencyItem);

            currencyItem.querySelector('.remove-currency').addEventListener('click', function(e) {
                e.stopPropagation();
                removeCurrency(symbol);
            });
        });
    }

    function removeCurrency(symbol) {
        selectedCurrencies = selectedCurrencies.filter(s => s !== symbol);
        updateCurrenciesDisplay();
        saveToLocalStorage();
        syncToBackend();
    }

    // Amount
    const amountInput = document.getElementById('amountInput');

    let amountPrev = amountInput.value;

    if (document.getElementById('amountWrapper')) {
        document.getElementById('amountWrapper').addEventListener('click', function() {
            amountInput.focus();
        });
    }

    amountInput.addEventListener('input', function(e) {
        const value = e.target.value.replace(/[^0-9]/g, '');
        e.target.value = value;
    });

    amountInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') e.target.blur();
    });

    amountInput.addEventListener('blur', function(e) {
        const value = e.target.value || amountPrev;
        e.target.value = value;
        amountPrev = value;
        // Persist investment amount
        saveToLocalStorage();
        syncToBackend();
    });

    // Risk — recalculates client-side for instant feedback after changing investment.
    // The server recomputes the real value every 2s via the metrics poll, which
    // will reconcile, but this gives the user immediate visual response.
    const riskInput = document.getElementById('riskInput');
    const riskDisplay = document.getElementById('riskDisplay');

    function estimateRiskFromInvestment() {
        const amount = parseFloat(document.getElementById('amountInput').value) || 0;
        // Mirror the server-side formula: exposure = amount * trade_size (default 0.1)
        // investment_risk = min(log10(exposure+1) * 10, 40)
        // Then weight it at 0.25 alongside baseline factors.
        const tradeSize = 0.1;
        const exposure = amount * tradeSize;
        const investmentRisk = exposure > 0 ? Math.min(Math.log10(exposure + 1) * 10, 40) : 0;
        // Baseline factors when no trades exist: loss=10, vol=5, conf=15, tol=10
        const baseline = 10 * 0.20 + 5 * 0.15 + investmentRisk * 0.25 + 15 * 0.20 + 10 * 0.20;
        const risk = Math.max(0, Math.min(100, baseline));
        const formatted = risk.toFixed(1);
        if (riskInput) riskInput.value = formatted;
        if (riskDisplay) riskDisplay.textContent = formatted + '%';
    }

    document.getElementById('amountInput').addEventListener('blur', estimateRiskFromInvestment);

    // ========== LOAD SAVED PREFERENCES ==========
    loadPreferences();

});
