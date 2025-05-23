document.querySelectorAll('.animate-on-scroll').forEach(el => {
    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) entry.target.classList.add('animated-visible');
        });
    });
    observer.observe(el);
});