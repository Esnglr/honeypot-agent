from kafka import KafkaConsumer
import json
from utils.logger import get_logger
from agents.MPT_file_system_creation_agent_debugged import AutonomousFileAgent
from kafka.topics import Topics

class FileSystemConsumer:
    def __init__(self, bootstrap_servers="localhost:9092", group_id="fs-agent"):
        self.logger = get_logger("fs-consumer")
        self.consumer = KafkaConsumer(
            Topics.AGENT_TASKS_FS,
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            group_id=group_id,
            value_deseriaclizer=lambda m: json.loads(m.decode("utf-8"))
        )
        self.agent = AutonomousFileAgent()

    def start(self):
        self.logger.info("FileSytemConsumer strated, waiting for tasks...")
        for message in self.consumer:
            task = message.value
            self.logger.info(f"Received task: {task}")
            action = task.get("action")
            try:
                if action == "":
                    return "a"
                elif action == "":
                    return None
                else:
                    self.logger.warning(f"Unknown action '{action}' for FileSystemConsumer")
            except EXception as ex:
                self.logger.error(f"Error handling file system task: {ex}")
