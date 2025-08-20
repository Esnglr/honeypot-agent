import json
import time
from kafka import KafkaConsumer as KConsumer
from utils.logger import get_logger
import uuid
# dashboard kisminda poll_once ve listen_forever kullanmak daha pratik olabilir duzenlesek o sekilde iyi olur
# self.consumer.listen_forever(callback=self.consumer.return_list)

class KafkaConsumer:
    """
    Wrapper for Kafka consumer with JSON deserialization and reconnect logic.
    """

    def __init__(self, topic: str, bootstrap_servers="localhost:9092", retries=5, retry_interval=3,auto_offset_reset='earliest', **kwargs):
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = f"{uuid.uuid4()}"
        self.retries = retries
        self.retry_interval = retry_interval
        self.logger = get_logger(f"KafkaConsumer[{topic}]")
        self.consumer = None
        self._connect()
        self.obj = []

    def _connect(self):
        """
        Connect to Kafka broker with retry logic.
        """
        attempt = 0
        while attempt < self.retries:
            try:
                # isim karisikligi sonsuz dongu yaratir dikkat
                self.consumer = KConsumer(
                    self.topic,
                    bootstrap_servers=self.bootstrap_servers,
                    group_id=self.group_id,
                    value_deserializer=self._safe_json,
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

    def _safe_json(self, message:bytes) :
        if not message:
            self.logger.debug("Received empty message")
            return None

        try:
            decoded = message.decode('utf-8').strip()
            if not decoded:
                self.logger.warning("Empty message after decoding")
                return None
                
            return json.loads(decoded)
            
        except UnicodeDecodeError as e:
            self.logger.error(f"Message decoding failed: {e}")
            return {"error": "Invalid message encoding"}
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON: {e.doc} | Error: {e}")
            return {"error": f"Invalid JSON: {str(e)}"}
            
        except Exception as e:
            self.logger.error(f"Unexpected deserialization error: {e}")
            return {"error": str(e)}

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
        print(messages)
        return messages

    def close(self):
        """
        Close the Kafka consumer connection.
        """
        if self.consumer:
            self.consumer.close()
            self.logger.info("Kafka consumer connection closed.")

    def __iter__(self):
        return self.consumer.__iter__()

    def __next__(self):
        return next(self.consumer)

    def return_list(self, msg):
        self.obj.insert(0, msg)
        return self.obj