document.addEventListener('DOMContentLoaded', function() {

    // ALL YOUR CODE HERE

    // ========== CURRENCIES DATABASE ==========
    const allCurrencies = [
        { symbol: 'EUR', name: 'Euro', icon: '€', color: 'from-[#3b82f6] to-[#2563eb]' },
        { symbol: 'USD', name: 'Dollar', icon: '$', color: 'from-[#22c55e] to-[#16a34a]' },
        { symbol: 'BTC', name: 'Bitcoin', icon: '₿', color: 'from-[#fb923c] to-[#ea580c]' },
        { symbol: 'ETH', name: 'Ethereum', icon: 'Ξ', color: 'from-[#a855f7] to-[#7c3aed]' },
    ];

    let selectedCurrencies = [];

    // ========== CURRENCY SEARCH ==========
    const currencySearch = document.getElementById('currencySearch');
    const currencyDropdown = document.getElementById('currencyDropdown');
    const selectedCurrenciesContainer = document.getElementById('selectedCurrencies');

    selectedCurrenciesContainer.innerHTML = '<div class="w-full text-center text-[#64748b] text-sm">No currencies selected</div>';

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
        const name = resultElement.dataset.name;
        const icon = resultElement.dataset.icon;
        const color = resultElement.dataset.color;

        if (selectedCurrencies.includes(symbol)) return; // Already selected
        if (selectedCurrencies.length >= 4) {
            alert('Maximum 4 currencies allowed');
            return;
        }

        selectedCurrencies.push(symbol);
        updateCurrenciesDisplay();

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
    }

    // Função para formatar valores monetários
    function formatCurrency(value) {
         return '€' + parseInt(value).toLocaleString('pt-PT');
    }

    // Aimed Profit
    const aimedProfitInput = document.getElementById('aimedProfitInput');
    const aimedProfitDisplay = document.getElementById('aimedProfitDisplay');

    let aimedProfitPrev = aimedProfitInput.value;

    document.getElementById('aimedProfitWrapper').addEventListener('click', function() {
        aimedProfitInput.focus();
    });

    aimedProfitInput.addEventListener('focus', function() {
        aimedProfitPrev = aimedProfitInput.value;
        aimedProfitDisplay.style.opacity = '0';
        aimedProfitInput.value = '';
    });

    aimedProfitInput.addEventListener('input', function(e) {
        const value = e.target.value.replace(/[^0-9]/g, '');
        e.target.value = value;
    });

    aimedProfitInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') e.target.blur();
    });

    aimedProfitInput.addEventListener('blur', function(e) {
        const value = e.target.value || aimedProfitPrev;
        e.target.value = value;
        aimedProfitDisplay.textContent = formatCurrency(value);
        aimedProfitDisplay.style.opacity = '';
    });

    // Amount
    const amountInput = document.getElementById('amountInput');
    const amountDisplay = document.getElementById('amountDisplay');

    let amountPrev = amountInput.value;

    document.getElementById('amountWrapper').addEventListener('click', function() {
        amountInput.focus();
    });

    amountInput.addEventListener('focus', function() {
        amountPrev = amountInput.value;
        amountDisplay.style.opacity = '0';
        amountInput.value = '';
    });

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
        amountDisplay.textContent = formatCurrency(value);
        amountDisplay.style.opacity = '';
    });

    // Risk
    const riskInput = document.getElementById('riskInput');
    const riskDisplay = document.getElementById('riskDisplay');

    function calculateRisk() {
        const profit = parseFloat(document.getElementById('aimedProfitInput').value) || 0;
        const amount = parseFloat(document.getElementById('amountInput').value) || 0;

        let riskValue = 0;
        if (amount > 0) {
            //substituir depois pela fórmula de cálculo de risco
            riskValue = (profit / amount) * 100;
        }

        const formattedRisk = riskValue === 0 ? '0' : riskValue.toFixed(2);
        if (riskInput) riskInput.value = formattedRisk;
        if (riskDisplay) riskDisplay.textContent = formattedRisk + '%';
    }

    document.getElementById('aimedProfitInput').addEventListener('blur', calculateRisk);
    document.getElementById('amountInput').addEventListener('blur', calculateRisk);

    // Chart tooltip
    const tooltip = document.getElementById('chartTooltip');
    const tooltipMonth = document.getElementById('tooltipMonth');
    const tooltipValue = document.getElementById('tooltipValue');
    const chartContainer = document.querySelector('.relative.h-72');

    document.querySelectorAll('.chart-point[data-month]').forEach(point => {
        point.addEventListener('mouseenter', function(e) {
            tooltipMonth.textContent = this.dataset.month;
            tooltipValue.textContent = '$' + this.dataset.value;

            const svg = this.closest('svg');
            const rect = svg.getBoundingClientRect();
            const containerRect = chartContainer.getBoundingClientRect();
            const cx = parseFloat(this.getAttribute('cx'));
            const cy = parseFloat(this.getAttribute('cy'));
            const viewBox = svg.viewBox.baseVal;

            const x = ((cx - viewBox.x) / viewBox.width) * rect.width;
            const y = (cy / viewBox.height) * rect.height;

            tooltip.classList.remove('hidden');
            tooltip.style.left = (x - tooltip.offsetWidth / 2) + 'px';
            tooltip.style.top = (y - tooltip.offsetHeight - 12) + 'px';
        });

        point.addEventListener('mouseleave', function() {
            tooltip.classList.add('hidden');
        });
    });

});
