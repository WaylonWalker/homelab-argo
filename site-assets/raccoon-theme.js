(() => {
  const inlineThemedMascot = async () => {
    const image = document.querySelector('.docs-home-art > img[src="/raccoon.svg"]');
    if (!image) return;

    try {
      const response = await fetch(image.src, { credentials: 'same-origin' });
      if (!response.ok) return;

      const source = await response.text();
      const parsed = new DOMParser().parseFromString(source, 'image/svg+xml');
      if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') return;

      const svg = document.importNode(parsed.documentElement, true);
      svg.querySelectorAll('script').forEach((script) => script.remove());
      svg.style.setProperty('--raccoon-bg', 'transparent');
      svg.style.setProperty('--raccoon-accent', 'var(--color-primary)');
      image.replaceWith(svg);
    } catch {
      // Keep the original image visible if inline loading fails.
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inlineThemedMascot, { once: true });
  } else {
    inlineThemedMascot();
  }
})();
