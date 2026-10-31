(() => {
  const loadInlineSvg = async (src) => {
    const response = await fetch(src, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`Could not load ${src}`);

    const source = await response.text();
    const parsed = new DOMParser().parseFromString(source, 'image/svg+xml');
    if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') {
      throw new Error(`Invalid SVG at ${src}`);
    }

    const svg = document.importNode(parsed.documentElement, true);
    svg.querySelectorAll('script').forEach((script) => script.remove());
    svg.style.setProperty('--raccoon-accent', 'var(--color-primary)');
    return svg;
  };

  const inlineHomeArt = async () => {
    const image = document.querySelector('.docs-home-art > img[src="/raccoon.svg"]');
    if (!image) return;
    try {
      const svg = await loadInlineSvg(image.src);
      svg.style.setProperty('--raccoon-bg', 'transparent');
      image.replaceWith(svg);
    } catch {
      // Keep the original image visible if inline loading fails.
    }
  };

  const inlineHeaderMark = async () => {
    const title = document.querySelector('.site-header .site-title');
    if (!title || title.querySelector('.site-title-mark')) return;
    try {
      const svg = await loadInlineSvg('/raccoon-nav.svg');
      svg.classList.add('site-title-mark');
      svg.setAttribute('aria-hidden', 'true');
      svg.removeAttribute('role');
      title.prepend(svg);
    } catch {
      // The CSS image mark remains as a fallback.
    }
  };

  const initialize = () => {
    inlineHomeArt();
    inlineHeaderMark();
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
