import sys
import json
import time
from kafka.kafka_producer import KafkaProducer
from kafka.topics import ATTACKER_COMMANDS
from utils.id_generator import generate_session_id
from utils.logger import get_logger

class CommandCaptureAgent:

    def __init__(self, kafka_producer: KafkaProducer, session_id=None):
        self.kafka_producer = kafka_producer
        self.logger = get_logger("CommandCaptureAgent")
        self.session_id = session_id or generate_session_id()

    def capture_and_send(self, command: str, source_ip: str):
        
        message = {
            "type": "command",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_ip": source_ip,
            "session_id": self.session_id,
            "command": command.strip()
        }

        try:
            self.kafka_producer.send_message(ATTACKER_COMMANDS, message)
            self.logger.info(f"Command is sent to Kafka: {message}")
        except Exception as ex:
            self.logger.error(f"Failed to send to Kafka the command: {ex}")

    def run_interactive(self, source_ip: str):

        self.logger.info("CommandCaptureAgent is started.")
        try:
            while True:
                command = input("$ ")
                if command.strip().lower() in ("exit", "quit"):
                    break
                self.capture_and_send(command, source_ip)
        except KeyboardInterrupt:
            self.logger.info("CommandCaptureAgent is stopped by the hacker.")

