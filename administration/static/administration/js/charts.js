 document.addEventListener("DOMContentLoaded", function () {
    const ctx = document.getElementById("revenueChart").getContext("2d");
    const chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: [
          "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ],
        datasets: [{
          label: "Revenu total (€)",
          data: monthlyRevenue,
          borderColor: "rgba(75, 192, 192, 1)",
          backgroundColor: "rgba(75, 192, 192, 0.2)",
          tension: 0.3,
          fill: true,
          pointRadius: 5,
          pointHoverRadius: 7,
        }]
      },
      options: {
        responsive: true,
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: value => value + ' €'
            }
          }
        },
        plugins: {
          legend: { display: true },
          tooltip: {
            callbacks: {
              label: context => context.parsed.y + ' €'
            }
          }
        }
      }
    });
  });