document.addEventListener("DOMContentLoaded", function () {
  const totalRevenueElem = document.getElementById("total-revenue");
  const totalTaxesElem = document.getElementById("total-taxes");
  const totalPlatformElem = document.getElementById("total-platform");
  const totalPaymentElem = document.getElementById("total-payment");
  const totalRefundsElem = document.getElementById("total-refunds");
  const netProfitElem = document.getElementById("net-profit");
  const economyError = document.getElementById("economy-error");
  const economyChartElem = document.getElementById("economy-chart");

  try {
    // Compute totals
    const sum = (arr) => arr.reduce((a, b) => a + (parseFloat(b) || 0), 0);
    const totalRevenusBrut = sum(totalRevenuBrut);
    const totalRevenusNet = sum(totalRevenuNet);
    const admintotalRevenus = sum(admintotalRevenu);
    const totalTax = sum(taxes);
    const refunds = sum(totalRefunds);
    const platform = sum(platformEarnings);
    const payment = sum(paymentFees);

    totalRevenueElem.textContent = `€${totalRevenusBrut.toFixed(2)}`;
    totalTaxesElem.textContent = `€${totalTax.toFixed(2)}`;
    netProfitElem.textContent = `€${totalRevenusNet.toFixed(2)}`;
    totalRefundsElem.textContent = `€${refunds.toFixed(2)}`;
    totalPlatformElem.textContent = `€${platform.toFixed(2)}`;
    totalPaymentElem.textContent = `€${payment.toFixed(2)}`;

    const ctx = economyChartElem.getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Revenu Net",
            data: totalRevenuNet,
            backgroundColor: "#198754",
            stack: "stack1",
          },
          {
            label: "Revenu Conciergerie",
            data: admintotalRevenu,
            backgroundColor: "#0dcaf0",
            stack: "stack1",
          },
          {
            label: "Remboursements",
            data: totalRefunds,
            backgroundColor: "#dc3545",
            stack: "stack1",
          },
          {
            label: "Frais Plateforme",
            data: platformEarnings,
            backgroundColor: "#6c757d",
            stack: "stack1",
          },
          {
            label: "Frais de Paiement",
            data: paymentFees,
            backgroundColor: "#0d6efd",
            stack: "stack1",
          },
          {
            label: "Taxes",
            data: taxes,
            backgroundColor: "#f39c12",
            stack: "stack1",
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          tooltip: {
            mode: "index",
            intersect: false,
          },
          legend: {
            position: "top",
          },
          title: {
            display: true,
            text: "Vue mensuelle empilée des revenus (Net, Remboursements, Taxes & Frais)",
          },
        },
        scales: {
          x: {
            stacked: true,
          },
          y: {
            stacked: true,
            beginAtZero: true,
            ticks: {
              callback: (value) => `€${value}`,
            },
          },
        },
        tooltip: {
          callbacks: {
            label: function (context) {
              return `${context.dataset.label}: €${context.raw.toFixed(2)}`;
            },
          },
          mode: "index",
          intersect: false,
        },
      },
    });
  } catch (error) {
    economyError.textContent =
      "Erreur lors du chargement des données. Veuillez réessayer.";
    economyError.style.display = "block";
    console.error("Revenue Chart Error:", error);
  }
});
