import { useEffect, useRef } from 'react';
import { CloseIcon } from './Icons';

interface ImageLightboxProps {
  src: string;
  alt?: string;
  onClose: () => void;
}

export function ImageLightbox({ src, alt = '题目图片', onClose }: ImageLightboxProps): JSX.Element {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div
      className="lightbox"
      role="dialog"
      aria-modal="true"
      aria-label="查看大图"
      onClick={onClose}
    >
      <button
        ref={closeButtonRef}
        type="button"
        className="lightbox-close"
        aria-label="关闭大图"
        onClick={onClose}
      >
        <CloseIcon size={22} />
      </button>
      <img
        src={src}
        alt={alt}
        className="lightbox-image"
        onClick={(event) => event.stopPropagation()}
      />
    </div>
  );
}
