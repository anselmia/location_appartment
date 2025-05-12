document.addEventListener("DOMContentLoaded", function () {
    const ctx = document.getElementById('trafficChart').getContext('2d');

    const trafficChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels, // ["2025-05-11", "2025-05-12", ...]
            datasets: [{
                label: 'Visites',
                data: data, // [5, 3, 9, ...]
                fill: true,
                tension: 0.3,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: selectedPeriod, // "day", "week", "month"
                        tooltipFormat: 'dd LLL yyyy',
                        displayFormats: {
                            day: 'dd LLL', // Exemple: 11 mai
                            week: 'dd LLL',
                            month: 'LLL yyyy'
                        }
                    },
                    adapters: {
                        date: {
                            locale: 'fr' // ⚠️ pour afficher en français (si tu veux)
                        }
                    },
                    ticks: {
                        source: 'auto',
                        autoSkip: true,
                        maxTicksLimit: 10,
                        callback: function (value, index, ticks) {
                            // Luxon formate les ticks si l'adapter fonctionne
                            return value;
                        }
                    },
                    title: {
                        display: true,
                        text: 'Date'
                    }
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Nombre de visites'
                    }
                }
            },
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
                legend: {
                    display: true
                }
            }
        }
    });
});