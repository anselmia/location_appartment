function toggleInlineFields(select) {
    const form = select.closest('form');
    const requiresMinNights = select.selectedOptions[0].dataset.minNights === '1';
    const requiresDaysBefore = select.selectedOptions[0].dataset.daysBefore === '1';
    const requiresDateRange = select.selectedOptions[0].dataset.dateRange === '1';

    // Safely toggle the display of the required fields
    const minNightsField = form.querySelector('.min-nights-field');
    const daysBeforeField = form.querySelector('.days-before-field');
    const startDateField = form.querySelector('.start-date-field');
    const endDateField = form.querySelector('.end-date-field');

    if (minNightsField) {
        minNightsField.style.display = requiresMinNights ? 'inline-block' : 'none';
    }
    if (daysBeforeField) {
        daysBeforeField.style.display = requiresDaysBefore ? 'inline-block' : 'none';
    }
    if (startDateField && endDateField) {
        startDateField.style.display = endDateField.style.display = requiresDateRange ? 'inline-block' : 'none';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Apply to new discount form
    const createFormSelect = document.querySelector('#discount-type-select');
    if (createFormSelect) {
        toggleInlineFields(createFormSelect);
        createFormSelect.addEventListener('change', () => toggleInlineFields(createFormSelect));
    }

    // Apply to all discount type selects in the existing discount list
    document.querySelectorAll('.discount-type-select').forEach(select => {
        toggleInlineFields(select);
        select.addEventListener('change', () => toggleInlineFields(select));
    });
});
