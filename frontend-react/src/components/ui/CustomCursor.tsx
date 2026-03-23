import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

type CursorState = {
  dotX: number;
  dotY: number;
  ringX: number;
  ringY: number;
  scale: number;
  visible: boolean;
  pressed: boolean;
};

function isInteractive(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;

  return Boolean(
    target.closest(
      'a, button, [role="button"], input[type="button"], input[type="submit"], input[type="reset"], .cursor-hover'
    )
  );
}

function CursorCore() {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);

  const stateRef = useRef<CursorState>({
    dotX: 0,
    dotY: 0,
    ringX: 0,
    ringY: 0,
    scale: 1,
    visible: true,
    pressed: false,
  });

  useEffect(() => {
    document.body.classList.add('custom-cursor-enabled');

    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    stateRef.current.dotX = centerX;
    stateRef.current.dotY = centerY;
    stateRef.current.ringX = centerX;
    stateRef.current.ringY = centerY;

    const render = () => {
      const dot = dotRef.current;
      const ring = ringRef.current;
      if (!dot || !ring) {
        frameRef.current = window.requestAnimationFrame(render);
        return;
      }

      const state = stateRef.current;

      state.ringX += (state.dotX - state.ringX) * 0.18;
      state.ringY += (state.dotY - state.ringY) * 0.18;

      const dotScale = state.pressed ? 0.9 : 1;
      const ringScale = state.scale * (state.pressed ? 0.88 : 1);

      dot.style.transform = `translate(${state.dotX}px, ${state.dotY}px) translate(-50%, -50%) scale(${dotScale})`;
      ring.style.transform = `translate(${state.ringX}px, ${state.ringY}px) translate(-50%, -50%) scale(${ringScale})`;

      dot.style.opacity = state.visible ? '1' : '0';
      ring.style.opacity = state.visible ? '1' : '0';

      frameRef.current = window.requestAnimationFrame(render);
    };

    const onMove = (e: MouseEvent) => {
      stateRef.current.dotX = e.clientX;
      stateRef.current.dotY = e.clientY;
      stateRef.current.visible = true;
      stateRef.current.scale = isInteractive(e.target) ? 1.45 : 1;
    };

    const onDown = () => {
      stateRef.current.pressed = true;
    };

    const onUp = () => {
      stateRef.current.pressed = false;
    };

    const onLeave = () => {
      stateRef.current.visible = true;
    };

    const onEnter = () => {
      stateRef.current.visible = true;
    };

    frameRef.current = window.requestAnimationFrame(render);

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mousedown', onDown);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('mouseleave', onLeave);
    window.addEventListener('mouseenter', onEnter);

    return () => {
      document.body.classList.remove('custom-cursor-enabled');

      if (frameRef.current) {
        window.cancelAnimationFrame(frameRef.current);
      }

      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('mouseleave', onLeave);
      window.removeEventListener('mouseenter', onEnter);
    };
  }, []);

  return (
    <>
      <div
        ref={ringRef}
        aria-hidden="true"
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: 34,
          height: 34,
          borderRadius: '9999px',
          border: '1.5px solid rgba(120, 179, 186, 0.65)',
          background: 'rgba(120, 179, 186, 0.08)',
          boxShadow: '0 0 24px rgba(120, 179, 186, 0.12)',
          pointerEvents: 'none',
          zIndex: 2147483646,
          opacity: 1,
          transform: 'translate(-50%, -50%) scale(1)',
          transition: 'opacity 0.2s ease',
          willChange: 'transform, opacity',
          backdropFilter: 'blur(2px)',
        }}
      />
      <div
        ref={dotRef}
        aria-hidden="true"
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: 8,
          height: 8,
          borderRadius: '9999px',
          background: '#78B3BA',
          boxShadow: '0 0 14px rgba(120, 179, 186, 0.35)',
          pointerEvents: 'none',
          zIndex: 2147483647,
          opacity: 1,
          transform: 'translate(-50%, -50%) scale(1)',
          transition: 'opacity 0.2s ease',
          willChange: 'transform, opacity',
        }}
      />
    </>
  );
}

export default function CustomCursor() {
  if (typeof document === 'undefined') return null;
  return createPortal(<CursorCore />, document.body);
}