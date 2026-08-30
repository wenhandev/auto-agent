/** Stubs for shared client modules when the web SPA build compiles without Tauri deps. */
declare module "@tauri-apps/api/event" {
  export function listen<T>(
    event: string,
    handler: (event: { payload: T }) => void,
  ): Promise<() => void>;
}

declare module "@tauri-apps/api/window" {
  export function getCurrentWindow(): {
    show(): Promise<void>;
    setFocus(): Promise<void>;
  };
}

declare module "@tauri-apps/plugin-opener" {
  export function openUrl(url: string): Promise<void>;
}
