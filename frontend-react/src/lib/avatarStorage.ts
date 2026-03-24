/**
 * Local-only avatar: stored in localStorage as data URL (no backend).
 * Images are resized/compressed to avoid quota errors.
 */
const STORAGE_PREFIX = 'ami_avatar_';
const MAX_EDGE = 256;
const JPEG_QUALITY = 0.82;

function key(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`;
}

export function getAvatarDataUrl(userId: string | null): string | null {
  if (!userId) return null;
  try {
    return localStorage.getItem(key(userId));
  } catch {
    return null;
  }
}

export function clearAvatar(userId: string | null): void {
  if (!userId) return;
  try {
    localStorage.removeItem(key(userId));
  } catch {
    // ignore
  }
}

/** Resize to max edge and export as JPEG data URL to keep storage small */
function fileToCompressedDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      let { width, height } = img;
      if (width <= 0 || height <= 0) {
        reject(new Error('Invalid image'));
        return;
      }
      if (width > MAX_EDGE || height > MAX_EDGE) {
        if (width >= height) {
          height = Math.round((height * MAX_EDGE) / width);
          width = MAX_EDGE;
        } else {
          width = Math.round((width * MAX_EDGE) / height);
          height = MAX_EDGE;
        }
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject(new Error('Canvas not supported'));
        return;
      }
      ctx.drawImage(img, 0, 0, width, height);
      try {
        const dataUrl = canvas.toDataURL('image/jpeg', JPEG_QUALITY);
        resolve(dataUrl);
      } catch {
        reject(new Error('Could not encode image'));
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Failed to load image'));
    };
    img.src = url;
  });
}

/**
 * Read file, compress, store. Returns error message if storage fails.
 */
export async function setAvatarFromFile(
  userId: string,
  file: File,
): Promise<{ ok: true } | { ok: false; error: string }> {
  if (!file.type.startsWith('image/')) {
    return { ok: false, error: 'Please choose an image file.' };
  }
  try {
    const dataUrl = await fileToCompressedDataUrl(file);
    try {
      localStorage.setItem(key(userId), dataUrl);
    } catch {
      return {
        ok: false,
        error: 'Image still too large for browser storage. Try a smaller image.',
      };
    }
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : 'Could not process image.',
    };
  }
}
