const flexLevels = [0, 1, 2, 3, 7];
let currentFlex = 0;
const currentYear = new Date().getFullYear();
let lastFormattedRange = '';

const picker = new Litepicker({
    element: document.getElementById('datepicker'),
    singleMode: false,
    numberOfMonths: 2,
    numberOfColumns: 2,
    lang: 'fr-FR',
    format: '',
    autoApply: true,
    dropdowns: {
        minYear: currentYear,
        maxYear: currentYear + 1,
        months: true,
        years: true
    },
    setup: (picker) => {
        picker.on('selected', (start, end) => {
            // Format ISO pour le backend
            document.getElementById('start_date').value = start.format('YYYY-MM-DD');
            document.getElementById('end_date').value = end.format('YYYY-MM-DD');

            // Format affiché à l'utilisateur dans l'input visible
            const monthNames = [
                'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'
            ];

            const startDay = start.dateInstance.getDate();
            const startMonth = monthNames[start.dateInstance.getMonth()];
            const endDay = end.dateInstance.getDate();
            const endMonth = monthNames[end.dateInstance.getMonth()];

            const formattedStart = `${startDay} ${startMonth}`;
            const formattedEnd = `${endDay} ${endMonth}`;

            lastFormattedRange = `${formattedStart} – ${formattedEnd}`;
            document.getElementById('datepicker').value = lastFormattedRange;
            picker.ui.querySelector('.container__main .container__footer .preview-date-range').textContent = '';
        });
    }
});

picker.on('hide', () => {
    if (lastFormattedRange) {
        document.getElementById('datepicker').value = lastFormattedRange;
    }
});

document.querySelectorAll('.flex-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.flex-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('flexibility').value = btn.dataset.flex;
    });
});

document.getElementById('destination-input').addEventListener('input', function () {
    const query = this.value;
    if (query.length < 2) return;

    fetch(`/cities/?q=${encodeURIComponent(query)}`)
        .then(response => response.text())
        .then(data => {
            document.getElementById('cities').innerHTML = data;
        });
});

document.querySelectorAll('.animate-on-scroll').forEach(el => {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) entry.target.classList.add('animated-visible');
      });
    });
    observer.observe(el);
  });


  document.getElementById('destination-input').addEventListener('input', function () {
    const query = this.value;
    if (query.length < 2) return;
  
    fetch(`/cities/?q=${encodeURIComponent(query)}`)
      .then(response => response.text())
      .then(data => {
        document.getElementById('cities').innerHTML = data;
      });
  });