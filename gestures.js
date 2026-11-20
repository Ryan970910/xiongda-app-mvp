export function restoreCollage(root, settings) {
  const wall = root.querySelector('.paste-window');
  if (wall) {
    wall.scrollLeft = settings.pan || 0;
    wall.scrollTop = settings.panY || 0;
  }
}
export function bindGestures(root, settings, select) {
  let drag = null,
    blockClickUntil = 0;
  root.addEventListener('pointerdown', (event) => {
    const el = event.target.closest('[data-swipe],.paste-window');
    if (!el || event.button !== 0) return;
    drag = {
      el,
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      scroll: el.scrollLeft,
      top: el.scrollTop,
      moved: false
    };
  });
  root.addEventListener('pointermove', (event) => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.x,
      dy = event.clientY - drag.y;
    const wall = drag.el.matches('.paste-window');
    if (!wall && !drag.moved && Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 10) {
      drag = null;
      return;
    }
    if (!drag.moved && Math.max(Math.abs(dx), wall ? Math.abs(dy) : 0) < 7) return;
    if (!drag.moved) drag.el.setPointerCapture(event.pointerId);
    drag.moved = true;
    if (wall) {
      drag.el.scrollLeft = drag.scroll - dx;
      drag.el.scrollTop = drag.top - dy;
    } else {
      drag.el.style.setProperty('--drag', Math.min(42, Math.max(-42, dx / 4)) + 'px');
      if (drag.el.dataset.swipe === 'leaf')
        drag.el.style.setProperty('--turn', Math.min(35, Math.max(-35, dx / 4)));
    }
  });
  function end(event) {
    if (!drag || drag.id !== event.pointerId) return;
    const d = drag;
    drag = null;
    if (d.el.hasPointerCapture(event.pointerId)) d.el.releasePointerCapture(event.pointerId);
    d.el.style.removeProperty('--drag');
    d.el.style.removeProperty('--turn');
    if (!d.moved) return;
    blockClickUntil = performance.now() + 220;
    if (d.el.matches('.paste-window')) {
      settings().pan = d.el.scrollLeft;
      settings().panY = d.el.scrollTop;
      return;
    }
    const dx = event.clientX - d.x;
    if (event.type === 'pointercancel' || Math.abs(dx) < 30) return;
    const i = Number(d.el.dataset.index),
      n = Number(d.el.dataset.count);
    select(d.el.dataset.swipe, Math.max(0, Math.min(n - 1, i + (dx < 0 ? 1 : -1))));
  }
  root.addEventListener('pointerup', end);
  root.addEventListener('pointercancel', end);
  window.addEventListener('pointerup', end);
  root.addEventListener(
    'click',
    (event) => {
      if (performance.now() < blockClickUntil) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
      const button = event.target.closest('[data-pan]');
      if (button) {
        const wall = root.querySelector('.paste-window');
        const dir = button.dataset.pan;
        wall.scrollBy({
          left: (Number(dir) || 0) * wall.clientWidth * 0.6,
          top: dir === 'up' ? -100 : dir === 'down' ? 100 : 0,
          behavior: 'instant'
        });
        settings().pan = wall.scrollLeft;
        settings().panY = wall.scrollTop;
      }
    },
    true
  );
  root.addEventListener(
    'scroll',
    (event) => {
      if (event.target.matches?.('.paste-window')) {
        settings().pan = event.target.scrollLeft;
        settings().panY = event.target.scrollTop;
      }
    },
    true
  );
  root.addEventListener('keydown', (event) => {
    if (
      event.target.matches('.paste-window') &&
      ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)
    ) {
      event.preventDefault();
      event.target.scrollBy({
        left: event.key === 'ArrowLeft' ? -160 : event.key === 'ArrowRight' ? 160 : 0,
        top: event.key === 'ArrowUp' ? -100 : event.key === 'ArrowDown' ? 100 : 0
      });
    }
  });
}
