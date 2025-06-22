function setStatusAndSubmit(status) {
  const statusInput = document.getElementById("statusInput");
  const form = document.getElementById("filterForm");
  if (statusInput && form) {
    statusInput.value = status;
    form.submit();
  }
}