let trafficChart = null; // Declare trafficChart globally

document.addEventListener("DOMContentLoaded", function () {
    const ctx = document.getElementById('trafficChart').getContext('2d');

    // Initialize the chart only if it doesn't exist
    if (!trafficChart) {
        trafficChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Visites',
                    data: data,
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
                                locale: 'fr' // For French locale, if desired
                            }
                        },
                        ticks: {
                            source: 'auto',
                            autoSkip: true,
                            maxTicksLimit: 10,
                            callback: function (value, index, ticks) {
                                // Ensure that the value is a valid date string for Chart.js
                                return new Date(value).toLocaleDateString('fr-FR');// Format as 'YYYY-MM-DD'
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
    }
});

function submitPeriodForm() {
    const period = document.getElementById('period').value; // Get selected period (day, week, month)

    // Send POST request to the server with the selected period
    fetch('/admin-area/traffic/', {
            method: 'POST',
            body: new URLSearchParams({
                'period': period,
                'csrfmiddlewaretoken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }),
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
        })
        .then(response => response.json()) // Parse JSON response
        .then(data => {
            // Ensure the trafficChart exists before updating
            if (trafficChart) {
                trafficChart.data.labels = data.labels;
                trafficChart.data.datasets[0].data = data.data;
                trafficChart.update();
            } else {
                console.error('Chart is not initialized yet.');
            }
        })
        .catch(error => console.error('Error fetching data:', error));
}