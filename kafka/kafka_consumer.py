import json
import time
from kafka import KafkaConsumer as KConsumer
from utils.logger import get_logger

class KafkaConsumer:
    """
    Wrapper for Kafka consumer with JSON deserialization and reconnect logic.
    """

    def __init__(self, topic: str, bootstrap_servers="localhost:9092", group_id="honeypot_group", retries=5, retry_interval=3):
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.retries = retries
        self.retry_interval = retry_interval
        self.logger = get_logger(f"KafkaConsumer[{topic}]")
        self.consumer = None
        self._connect()

    def _connect(self):
        """
        Connect to Kafka broker with retry logic.
        """
        attempt = 0
        while attempt < self.retries:
            try:
                self.consumer = KConsumer(
                    self.topic,
                    bootstrap_servers=self.bootstrap_servers,
                    group_id=self.group_id,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    auto_offset_reset="earliest",  # Read from beginning if no offset stored
                    enable_auto_commit=True
                )
                self.logger.info(f"Connected to Kafka topic '{self.topic}' at {self.bootstrap_servers}")
                return
            except Exception as e:
                attempt += 1
                self.logger.error(f"Failed to connect to Kafka: {e} (attempt {attempt}/{self.retries})")
                time.sleep(self.retry_interval)
        raise ConnectionError(f"Unable to connect to Kafka after {self.retries} attempts")

    def listen_forever(self, callback):
        """
        Listen to messages indefinitely and process them with a callback function.
        :param callback: Function that takes a single argument (the message dict).
        """
        self.logger.info(f"Listening for messages on topic '{self.topic}'")
        try:
            for message in self.consumer:
                self.logger.debug(f"Received message from '{self.topic}': {message.value}")
                try:
                    callback(message.value)
                except Exception as e:
                    self.logger.error(f"Error in message callback: {e}")
        except KeyboardInterrupt:
            self.logger.info("Consumer stopped by user.")
        finally:
            self.close()

    def poll_once(self, timeout_ms=1000):
        """
        Poll the topic for new messages once (non-blocking).
        Returns a list of messages.
        """
        messages = []
        raw_msgs = self.consumer.poll(timeout_ms=timeout_ms)
        for tp, msg_list in raw_msgs.items():
            for msg in msg_list:
                messages.append(msg.value)
        return messages

    def close(self):
        """
        Close the Kafka consumer connection.
        """
        if self.consumer:
            self.consumer.close()
            self.logger.info("Kafka consumer connection closed.")