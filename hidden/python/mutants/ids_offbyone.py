"""ID helpers."""


def format_id(prefix, n):
    """Builds IDs like "usr_000001" from a resource prefix and sequence."""
    return f"{prefix}_{n + 1:06d}"
