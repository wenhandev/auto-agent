## ADDED Requirements

### Requirement: Home is the default signed-in landing page

The desktop app SHALL route authenticated users to a Home page at `/` that emphasizes workflows and local runs, not developer preflight diagnostics.

#### Scenario: Post-login navigation

- **WHEN** a user completes sign-in and is approved
- **THEN** the app navigates to `/` showing the Home page with primary actions to open Workflows and Runs

### Requirement: User-facing device status

Technical preflight check identifiers (e.g. `playwright_installed`, `chromium_binary`) SHALL NOT be shown as primary labels in default desktop UI. The app SHALL present human-readable status labels and a summary state (Ready, Limited, Setup needed).

#### Scenario: Overview displays friendly labels

- **WHEN** the user views device status from Home or Settings
- **THEN** checks are labeled with user-facing names such as "Chromium browser" rather than internal IDs

### Requirement: Production startup waits on local runtime only

When the cloud URL is baked into the production installer, the startup gate SHALL consider the app ready for login once the local embedded runtime is healthy, without blocking on remote cloud health during splash.

#### Scenario: Splash dismisses when runtime is up

- **WHEN** the production app launches and the embedded runtime responds healthy
- **THEN** the splash screen dismisses even if remote cloud health has not yet been verified

### Requirement: Desktop branding

The signed-in shell SHALL display the product name "Auto Agent" without the suffix "Client" in primary navigation chrome.

#### Scenario: Sidebar title

- **WHEN** the user views the main desktop shell
- **THEN** the sidebar header reads "Auto Agent"

### Requirement: Production login without cloud URL field

When the installer bakes in the production cloud URL, the login screen SHALL NOT require or display a cloud URL input; sign-in SHALL use OAuth or org-configured methods only.

#### Scenario: Google OAuth login

- **WHEN** the user opens the production desktop login screen
- **THEN** they can sign in with Google without entering a server URL

## MODIFIED Requirements

### Requirement: Desktop startup gate

The desktop app SHALL wait for required local services before showing the main authenticated UI. In production builds with a remote cloud URL, required local services SHALL mean the embedded runtime only. In local development builds, required local services MAY include both local cloud and embedded runtime.

#### Scenario: Production runtime-only gate

- **WHEN** the app is a production build with baked-in remote cloud URL
- **THEN** the startup gate completes when the embedded runtime is healthy

#### Scenario: Dev dual-service gate

- **WHEN** the app runs in development against local cloud `127.0.0.1:8001`
- **THEN** the startup gate waits for both local cloud and embedded runtime before login
