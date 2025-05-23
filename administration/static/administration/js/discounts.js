function toggleInlineFields(select) {
    const form = select.closest('form');
    const selected = select.options[select.selectedIndex];
    if (!selected) return;
  
    // Read booleans from option attributes
    const showMinNights     = selected.dataset.minNights === "1";
    const showDaysBefore    = selected.dataset.daysBefore === "1";
    const showDateRange     = selected.dataset.dateRange === "1";

    // Map actual fields you have
    const visibilityMap = {
    '.min-nights-field': showMinNights,
    '.days-before-min-field': showDaysBefore,
    '.days-before-max-field': showDaysBefore, // You might want both
    '.start-date-field': showDateRange,
    '.end-date-field': showDateRange,
    '.exact-nights-field': false  // If not supported, always hide
    };
    
    // Toggle each field group
    Object.entries(visibilityMap).forEach(([selector, show]) => {
      const el = form.querySelector(selector);
      if (el) el.style.display = show ? "block" : "none";
    });
  }
  
  document.addEventListener("DOMContentLoaded", () => {
    const select = document.querySelector("#discount-type-select");  // ✅ match your template ID
    if (select) {
      toggleInlineFields(select);
      select.addEventListener("change", () => toggleInlineFields(select));
    }
  });
  