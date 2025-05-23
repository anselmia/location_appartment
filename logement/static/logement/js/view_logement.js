document.querySelectorAll('.logement-description p').forEach(p => {
    if (p.innerText.trim().startsWith('-')) {
        p.classList.add('is-list');
    }
});

document.addEventListener("DOMContentLoaded", function () {
    const desc = document.getElementById("logementDescription");
    const toggleBtn = document.getElementById("toggleDescription");

    let isExpanded = false;

    toggleBtn.addEventListener("click", function () {
        isExpanded = !isExpanded;
        desc.classList.toggle("collapsed", !isExpanded);
        toggleBtn.textContent = isExpanded ? "Voir moins" : "Voir plus";
    });
});