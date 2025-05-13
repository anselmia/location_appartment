const modal = document.getElementById('imageModal');
const modalImage = document.getElementById('modalImage');
const modalPrev = document.getElementById('modalPrev');
const modalNext = document.getElementById('modalNext');
const closeModal = document.getElementById('closeModal');

// Gather all images into an array
const galleryImages = Array.from(document.querySelectorAll('.image-gallery img'));
let currentIndex = 0;

function showModal(index) {
    currentIndex = index;
    modalImage.src = galleryImages[currentIndex].src;
    modal.style.display = 'flex';
}

galleryImages.forEach((img, index) => {
    img.addEventListener('click', () => {
        showModal(index);
    });
});

closeModal.addEventListener('click', () => {
    modal.style.display = 'none';
});


modalPrev.addEventListener('click', () => {
    currentIndex = (currentIndex - 1 + galleryImages.length) % galleryImages.length;
    showModal(currentIndex);
});

modalNext.addEventListener('click', () => {
    currentIndex = (currentIndex + 1) % galleryImages.length;
    showModal(currentIndex);
});