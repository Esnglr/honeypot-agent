import uuid
import random
import string

class Id:
    def generate_session_id() -> str:
        return f"sess-{uuid.uuid4()}"

    def generate_task_id() -> str:
        return f"task-{uuid.uuid4()}"

    def generate_group_id() -> str:
        return f"group-{uuid.uuid4()}"

    def generate_short_id(length: int = 8) -> str:
        #Example: a7B9xYz2
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))