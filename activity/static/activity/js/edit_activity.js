document.addEventListener("DOMContentLoaded", function() {
    const fixedSlotsCheckbox = document.getElementById("id_fixed_slots");
    const manualDiv = document.getElementById("manual-slots-div");
    const readyDiv = document.getElementById("ready-period-div");
    const manualInput = document.getElementById("id_manual_time_slots");
    const readyInput = document.getElementById("id_ready_period");

    function toggleSlotsFields() {
        if (fixedSlotsCheckbox.checked) {
            manualDiv.style.display = "block";
            readyDiv.style.display = "none";
            // Reset ready_period field
            if (readyInput) readyInput.value = "";
        } else {
            manualDiv.style.display = "none";
            readyDiv.style.display = "block";
            // Reset manual_time_slots field
            if (manualInput) manualInput.value = "";
        }
    }

    if (fixedSlotsCheckbox) {
        fixedSlotsCheckbox.addEventListener("change", toggleSlotsFields);
        // Initial state
        toggleSlotsFields();
    }
});