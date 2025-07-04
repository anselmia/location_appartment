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

    const rules = document.getElementById("logementRules");
    const toggleRules = document.getElementById("toggleRules");

    let isRulesExpanded = false;

    toggleRules.addEventListener("click", function () {
        isRulesExpanded = !isRulesExpanded;
        rules.classList.toggle("collapsed", !isRulesExpanded);
        toggleRules.textContent = isRulesExpanded ? "Voir moins" : "Voir plus";
    });

    // Show more comments functionality
    const btn = document.getElementById("showMoreCommentsBtn");
    if (btn) {
        btn.addEventListener("click", function() {
            document.querySelectorAll(".extra-comment").forEach(function(el) {
                el.classList.remove("d-none");
            });
            btn.style.display = "none";
        });
    }
});