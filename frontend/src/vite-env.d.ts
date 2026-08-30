/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_BYPASS?: string;
  readonly VITE_CLOUD_URL?: string;
  readonly VITE_APP_VERSION?: string;
  readonly VITE_CLIENT_RELEASES_URL?: string;
  readonly VITE_CLIENT_DOWNLOAD_MACOS?: string;
  readonly VITE_CLIENT_DOWNLOAD_WINDOWS?: string;
  readonly VITE_CLIENT_DOWNLOAD_LINUX?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.css";
