from kafka import KafkaConsumer
import json
from utils.logger import get_logger
from commands.wget import CommandWget
from kafka.topics import Topics

class WgetConsumer:
    def __init__(self, bootstrap_servers="localhost:9092", group_id="wget-agent"):
        self.logger = get_logger("wget-consumer")
        self.consumer = KafkaConsumer(
            Topics.AGENT_TASKS_WGET,
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8"))
        )
        self.agent = CommandWget()

    
    def start(self):
        self.logger.info("WgetConsumer started, waiting for tasks...")
        for message in self.consumer:
            task = message.value
            self.logger.info(f"Received task: {task}")
            action = task.get("action")
            if action == "run":
                try:
                    self.agent.start(**task)
                except Exception as ex:
                    self.logger.error(f"Error handling wget task: {ex}")
            else:
                self.logger.warning(f"Unknown action '{action}' for WgetConsumer")