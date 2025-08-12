import uuid
import random
import string

def generate_session_id() -> str:
    """
    Generates a unique session ID for attacker sessions.
    Example: sess-8f14e45f-ea3b-4b0b-bf42-bfe5dc8d94df
    """
    return f"sess-{uuid.uuid4()}"

def generate_task_id() -> str:
    """
    Generates a unique task ID for tasks assigned by the MasterAgent.
    Example: task-4a7d1ed4-8b16-4c77-a5cf-35e8f8c4f3b2
    """
    return f"task-{uuid.uuid4()}"

def generate_short_id(length: int = 8) -> str:
    """
    Generates a shorter, human-friendly random ID.
    Example: a7B9xYz2
    """
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))