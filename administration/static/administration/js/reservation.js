function filterStatus(status) {
    const rows = document.querySelectorAll('#reservationTable tbody tr');
    rows.forEach(row => {
        const rowStatus = row.getAttribute('data-status');
        row.style.display = (status === 'all' || rowStatus === status) ? '' : 'none';
    });
}

document.getElementById('searchInput').addEventListener('keyup', function () {
    const query = this.value.toLowerCase();
    const rows = document.querySelectorAll('#reservationTable tbody tr');
    rows.forEach(row => {
        const guestName = row.cells[1].textContent.toLowerCase();
        row.style.display = guestName.includes(query) ? '' : 'none';
    });
});