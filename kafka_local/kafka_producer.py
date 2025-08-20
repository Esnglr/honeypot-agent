import json
import time
from kafka import KafkaProducer as KProducer
from utils.logger import get_logger

class KafkaProducer:
    """
    Wrapper for Kafka producer with JSON serialization and simple reconnect logic.
    """

    def __init__(self, bootstrap_servers="localhost:9092", retries=5, retry_interval=3, value_serializer=None):
        self.bootstrap_servers = bootstrap_servers
        self.retries = retries
        self.retry_interval = retry_interval
        self.logger = get_logger("KafkaProducer")
        self.producer = None
        self._connect()

    def _connect(self):
        """
        Establish connection to Kafka broker with retry logic.
        """
        attempt = 0
        while attempt < self.retries:
            try:
                self.producer = KProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    acks="all"  # Wait for leader + replicas to acknowledge
                )
                self.logger.info(f"Connected to Kafka at {self.bootstrap_servers}")
                return
            except Exception as e:
                attempt += 1
                self.logger.error(f"Failed to connect to Kafka: {e} (attempt {attempt}/{self.retries})")
                time.sleep(self.retry_interval)
        raise ConnectionError(f"Unable to connect to Kafka after {self.retries} attempts")

    def send_message(self, topic: str, message: dict):
        """
        Send a message to the given Kafka topic.
        """
        if not self.producer:
            self.logger.error("Producer is not connected to Kafka")
            return

        try:
            self.producer.send(topic, message)
            self.producer.flush()
            self.logger.debug(f"Message sent to topic '{topic}': {message}")
        except Exception as e:
            self.logger.error(f"Failed to send message to Kafka: {e}")

    def flush(self, timeout=None):
        if hasattr(self.producer, 'flush'):
            return self.producer.flush(timeout=timeout)
        time.sleep(0.5)

    def close(self):
        """
        Close the Kafka producer connection.
        """
        if self.producer:
            self.flush()
            self.producer.close()
            self.logger.info("Kafka producer connection closed")

if __name__ == "__main__":
    producer = KafkaProducer()
    producer.send_message(topic="wget.tasks", message={"status":"success"})
    producer.flush()
    producer.close()