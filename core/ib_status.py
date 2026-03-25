IB_MAP: dict[str, str] = {
    "PendingSubmit": "submitted",
    "PreSubmitted":  "submitted",
    "Submitted":     "submitted",
    "Filled":        "filled",
    "Cancelled":     "cancelled",
    "Inactive":      "cancelled",
    "ApiCancelled":  "failed",
    "Error":         "failed",
}

TERMINAL: set[str] = {"filled", "cancelled", "failed"}


def normalize(raw: str) -> str:
    return IB_MAP.get(raw, "unknown")

def is_filled(raw: str) -> bool:
    return raw == "Filled"

def is_terminal(raw: str) -> bool:
    return normalize(raw) in TERMINAL
