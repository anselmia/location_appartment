const modal = document.getElementById("imageModal");
const modalImage = document.getElementById("modalImage");
const modalPrev = document.getElementById("modalPrev");
const modalNext = document.getElementById("modalNext");
const closeModal = document.getElementById("closeModal");

// Gather all images into an array
let currentIndex = 0;
const modalRoomLabel = document.getElementById("modalRoomLabel");

function showModal(index) {
  if (typeof allRoomLabels === "undefined" || !Array.isArray(allRoomLabels)) {
    var allRoomLabels = [];
  }
  currentIndex = index;
  modal.style.display = "flex";
  document.body.style.overflow = "hidden";

  modalImage.style.opacity = 0;
  setTimeout(() => {
    modalImage.src = allPhotoUrls[currentIndex];
    if (typeof modalRoomLabel !== "undefined" && modalRoomLabel) {
      modalRoomLabel.textContent = allRoomLabels[currentIndex] || "Général";
    }
    modalImage.style.opacity = 1;
  }, 100);
}

const thumbnails = document.querySelectorAll(".image-gallery img");
thumbnails.forEach((img, index) => {
  img.addEventListener("click", () => {
    showModal(index);
  });
});

closeModal.addEventListener("click", () => {
  modal.style.display = "none";
  document.body.style.overflow = "auto"; // re-enable scroll
});

modal.addEventListener("click", (e) => {
  if (e.target === modal) {
    modal.style.display = "none";
    document.body.style.overflow = "auto";
  }
});

modalPrev.addEventListener("click", () => {
  currentIndex = (currentIndex - 1 + allPhotoUrls.length) % allPhotoUrls.length;
  showModal(currentIndex);
});

modalNext.addEventListener("click", () => {
  currentIndex = (currentIndex + 1) % allPhotoUrls.length;
  showModal(currentIndex);
});

document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("imageModal");
  let touchStartX = 0;
  let touchEndX = 0;

  modal.addEventListener("touchstart", function (e) {
    touchStartX = e.changedTouches[0].screenX;
  });

  modal.addEventListener("touchend", function (e) {
    touchEndX = e.changedTouches[0].screenX;
    handleGesture();
  });

  function handleGesture() {
    const swipeThreshold = 50; // minimum px distance for a swipe
    const delta = touchEndX - touchStartX;

    if (Math.abs(delta) > swipeThreshold) {
      if (delta > 0) {
        document.getElementById("modalPrev").click(); // swipe right → previous image
      } else {
        document.getElementById("modalNext").click(); // swipe left → next image
      }
    }
  }
});
