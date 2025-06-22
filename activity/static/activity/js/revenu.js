document.addEventListener("DOMContentLoaded", function () {
  const totalRevenueElem = document.getElementById("total-revenue");
  const totalNetElem = document.getElementById("total-net");
  const totalPlatformElem = document.getElementById("total-platform");
  const totalPaymentElem = document.getElementById("total-payment");
  const totalRefundsElem = document.getElementById("total-refunds");
  const netProfitElem = document.getElementById("net-profit");
  const economyError = document.getElementById("economy-error");
  const economyChartElem = document.getElementById("economy-chart");

  try {   
    const monthIdx = selectedMonth - 1;

    totalRevenueElem.textContent = `€${(
      parseFloat(totalRevenuBrut[monthIdx]) || 0
    ).toFixed(2)}`;
    totalNetElem.textContent = `€${(
      parseFloat(totalRevenuNet[monthIdx]) || 0
    ).toFixed(2)}`;
    netProfitElem.textContent = `€${(
      parseFloat(totalTransfers[monthIdx]) || 0
    ).toFixed(2)}`;
    totalRefundsElem.textContent = `€${(
      parseFloat(totalRefunds[monthIdx]) || 0
    ).toFixed(2)}`;
    totalPlatformElem.textContent = `€${(
      parseFloat(platformEarnings[monthIdx]) || 0
    ).toFixed(2)}`;
    totalPaymentElem.textContent = `€${(
      parseFloat(paymentFees[monthIdx]) || 0
    ).toFixed(2)}`;

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
            text: "Vue mensuelle empilée des revenus (Net, Remboursements & Frais)",
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
    // Show a Bootstrap alert if available, otherwise fallback to inline message
    let alertBox = document.getElementById("revenue-alert");
    if (!alertBox) {
      alertBox = document.createElement("div");
      alertBox.id = "revenue-alert";
      alertBox.className = "alert alert-danger mt-3";
      alertBox.role = "alert";
      // Insert alert at the top of the economyChartElem's parent or body
      const revenueTitleElem = document.getElementById("revenu-title");
      if (revenueTitleElem && revenueTitleElem.parentNode) {
        revenueTitleElem.parentNode.insertBefore(alertBox, revenueTitleElem);
      } else if (economyChartElem && economyChartElem.parentNode) {
        economyChartElem.parentNode.insertBefore(alertBox, economyChartElem);
      } else {
        document.body.prepend(alertBox);
      }
    }
    alertBox.textContent =
      "Erreur lors du chargement des données. Veuillez réessayer.";
    alertBox.style.display = "block";
    console.error("Revenue Chart Error:", error);
  }
});
