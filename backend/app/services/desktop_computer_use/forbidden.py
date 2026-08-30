"""Hard-deny list for desktop Computer Use targets."""

from __future__ import annotations

# Bundle ids / name needles that must never be automated (Codex-aligned safety).
FORBIDDEN_BUNDLE_IDS: frozenset[str] = frozenset({
    # macOS
    "com.apple.Terminal",
    "com.apple.Terminal.savedState",
    "com.googlecode.iterm2",
    "net.kovidgoyal.kitty",
    "com.github.wez.wezterm",
    "com.apple.systempreferences",
    "com.apple.Preferences",
    "com.apple.SecurityAgent",
    "com.apple.frameworks.diskimages.diagent",
    "com.autoagent.desktop",
    "com.auto-agent.desktop",
    "com.wenhandev.auto-agent",
    # Windows executables / AUMIDs
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "windowsterminal.exe",
    "conhost.exe",
    "wt.exe",
    "consent.exe",
    "useraccountcontrolsettings.exe",
    "auto-agent-worker.exe",
    "auto agent.exe",
    "autoagent.exe",
})

FORBIDDEN_NAME_NEEDLES: tuple[str, ...] = (
    "terminal",
    "iterm",
    "kitty",
    "wezterm",
    "system settings",
    "system preferences",
    "securityagent",
    "windows powershell",
    "command prompt",
    "user account control",
    "auto agent",
    "auto-agent",
    "autoagent",
)


def normalize_app_key(app: str) -> str:
    return (app or "").strip().lower()


def is_forbidden_app(app: str, *, bundle_id: str = "", name: str = "") -> bool:
    """Return True if the app must be refused."""
    candidates = [
        normalize_app_key(app),
        normalize_app_key(bundle_id),
        normalize_app_key(name),
    ]
    for key in candidates:
        if not key:
            continue
        if key in {normalize_app_key(b) for b in FORBIDDEN_BUNDLE_IDS}:
            return True
        for needle in FORBIDDEN_NAME_NEEDLES:
            if needle in key:
                return True
    return False
