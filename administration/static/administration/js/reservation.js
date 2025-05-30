function filterStatus(status) {
    const rows = document.querySelectorAll("#reservationTable tbody tr");
    rows.forEach(row => {
        const rowStatus = row.getAttribute("data-status");
        if (status === "all" || rowStatus === status) {
            row.style.display = "";
        } else {
            row.style.display = "none";
        }
    });
}

document.getElementById('searchInput').addEventListener('keyup', function () {
    const query = this.value.toLowerCase();
    const rows = document.querySelectorAll('#reservationTable tbody tr');
    rows.forEach(row => {
        const guestName = row.cells[3].textContent.toLowerCase();
        row.style.display = guestName.includes(query) ? '' : 'none';
    });
});

document.querySelectorAll('select[name="year"], select[name="month"]').forEach(select => {
    select.addEventListener('change', () => select.form.submit());
});