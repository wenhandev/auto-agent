const STORAGE_KEY = "auto_agent_v1_api_key";

export function getV1ApiKey(): string | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value?.trim() || null;
  } catch {
    return null;
  }
}

export function setV1ApiKey(key: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, key.trim());
  } catch {
    // ignore quota / private mode
  }
}

export function clearV1ApiKey(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

/** Returns stored key or prompts once; null if user cancels. */
export function ensureV1ApiKey(): string | null {
  const stored = getV1ApiKey();
  if (stored) return stored;
  const entered = window.prompt(
    "Enter your v1 API key (Bearer token) for webhook management:",
  );
  if (!entered?.trim()) return null;
  setV1ApiKey(entered.trim());
  return entered.trim();
}
