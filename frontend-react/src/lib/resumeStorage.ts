/**
 * Persist resume filename and extracted text in localStorage so the data
 * survives navigation between Onboarding, Profile, and GoalsPage.
 */
const FILENAME_KEY = 'ami_resume_filename';
const TEXT_KEY = 'ami_resume_text';

export function getStoredResumeFileName(): string | null {
  try {
    return localStorage.getItem(FILENAME_KEY);
  } catch {
    return null;
  }
}

export function getStoredResumeText(): string {
  try {
    return localStorage.getItem(TEXT_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setStoredResume(fileName: string, text: string): void {
  try {
    localStorage.setItem(FILENAME_KEY, fileName);
    localStorage.setItem(TEXT_KEY, text);
  } catch {
    // quota exceeded or private browsing — silently ignore
  }
}

export function clearStoredResume(): void {
  try {
    localStorage.removeItem(FILENAME_KEY);
    localStorage.removeItem(TEXT_KEY);
  } catch {
    // ignore
  }
}
