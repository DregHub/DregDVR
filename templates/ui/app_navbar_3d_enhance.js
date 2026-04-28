function enhanceNavbar3D() {
  const iframe = document.querySelector('iframe[title="streamlit_navigation_bar.st_navbar"]');
  if (!iframe || !iframe.contentDocument) return;
  const doc = iframe.contentDocument;

  if (!doc.querySelector('[data-3d-glass]')) {
    const style = doc.createElement('style');
    style.setAttribute('data-3d-glass', 'true');
    style.textContent = `
      nav span::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 45%;
        background: linear-gradient(
          180deg,
          rgba(255,255,255,0.6),
          rgba(255,255,255,0.3),
          transparent
        );
        border-radius: 0 0 22px 22px;
        pointer-events: none;
      }

      nav span::after {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: 0 0 22px 22px;
        box-shadow: inset 0 0 18px rgba(255,255,255,0.18);
        pointer-events: none;
      }
    `;
    doc.head.appendChild(style);
  }

  const spans = doc.querySelectorAll('nav span');
  spans.forEach(span => {
    span.onpointerdown = () => span.classList.add('nav-active');
    span.onpointerup = () => span.classList.remove('nav-active');
    span.onpointerleave = () => span.classList.remove('nav-active');
    span.onpointercancel = () => span.classList.remove('nav-active');
  });
}

enhanceNavbar3D();
setTimeout(enhanceNavbar3D, 500);
setTimeout(enhanceNavbar3D, 1200);
