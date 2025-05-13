async function refreshData() {
    const loader = document.getElementById("economy-loader");
    loader.style.display = "inline-block";

    try {
        const year = document.getElementById('year-select').value;
        const month = document.getElementById('month-select').value;

        const data = await fetchEconomyData(year, month);
        updateSummary(data);
        renderChart(data.chart_labels, data.chart_values);
        document.getElementById("economy-error").style.display = "none";
    } catch (err) {
        // already handled
    } finally {
        loader.style.display = "none";
    }
}