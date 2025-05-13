function showError(message) {
    const errorBox = document.getElementById("economy-error");
    if (errorBox) {
        errorBox.textContent = message;
        errorBox.style.display = "block";
    } else {
        alert(message); // fallback
    }
}

async function fetchEconomyData(year, month) {
    try {
        const res = await fetch(`/admin-area/api/revenu/${logementId}/?year=${year}&month=${month}`);

        if (!res.ok) {
            throw new Error(`Erreur serveur: ${res.status}`);
        }

        const data = await res.json();

        if (!data || typeof data !== 'object') {
            throw new Error("Réponse invalide.");
        }

        return data;

    } catch (error) {
        console.error("Erreur lors du chargement des données :", error);
        showError("Impossible de charger les données économiques.");
        throw error;  // propagate if needed
    }
}

function updateSummary(data) {
    document.getElementById('total-revenue').textContent = `€${data.total_revenue.toFixed(2)}`;
    document.getElementById('total-taxes').textContent = `€${data.total_taxes.toFixed(2)}`;
    document.getElementById('net-profit').textContent = `€${data.net_profit.toFixed(2)}`;
}

let chart;

function renderChart(labels, revenues) {
    if (chart) chart.destroy();
    const ctx = document.getElementById('economy-chart');
    chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Revenus mensuels',
                data: revenues,
                backgroundColor: '#3b82f6'
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

async function refreshData() {
    try {
        const year = document.getElementById('year-select').value;
        const month = document.getElementById('month-select').value;

        const data = await fetchEconomyData(year, month);
        updateSummary(data);
        renderChart(data.chart_labels, data.chart_values);

        document.getElementById("economy-error").style.display = "none"; // hide if shown previously
    } catch (err) {
        // Error already handled in fetchEconomyData
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('year-select').addEventListener('change', refreshData);
    document.getElementById('month-select').addEventListener('change', refreshData);
    console.log("ah");
    refreshData(); // initial load
});