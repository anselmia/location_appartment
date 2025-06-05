document.addEventListener("DOMContentLoaded", function () {
  const heatmapTab = document.querySelector("#heatmap-tab");
  const heatmapPane = document.querySelector("#heatmap");

  if (!heatmapTab || !window.CalHeatmap || !dailyRevenueData) {
    console.warn("Préconditions non remplies pour la heatmap.");
    return;
  }

  let heatmapDrawn = false;

  function drawHeatmap() {
    if (heatmapDrawn) return;
    heatmapDrawn = true;

    const cal = new CalHeatmap();
    const legendPlugin = new CalHeatmap.plugins.Legend();

    cal.paint({
      itemSelector: "#heatmap-container",
      domain: "month",
      subDomain: "day",
      range: 12,
      start: new Date(window.selected_year, 0, 1),
      data: dailyRevenueData,
      scale: {
        color: {
          type: "linear",
          domain: [0, Math.max(...Object.values(dailyRevenueData)) || 1],
          scheme: "YlGnBu",
        },
      },
      plugins: [legendPlugin],
    }).then(() => {
      console.log("✅ Heatmap rendue !");
    });
  }

  // Quand l'utilisateur change d'onglet
  heatmapTab.addEventListener("shown.bs.tab", drawHeatmap);

  // Si déjà actif au chargement
  if (heatmapTab.classList.contains("active")) {
    drawHeatmap();
  }
});
