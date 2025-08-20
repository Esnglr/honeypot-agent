import os
import time
import json
from utils.logger import get_logger
from kafka_local.kafka_producer import KafkaProducer
from kafka_local import topics
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class TpotLogHandler(FileSystemEventHandler):
    def __init__(self):
        self.KAFKA_BROKER = 'localhost:9092'
        self.TOPIC = topics.ATTACKER_COMMANDS
        #self.LOG_DIR = '/var/log/tpot/'
        self.LOG_DIR = '/tmp/tpot_logs'

        self.producer =  KafkaProducer(
            bootstrap_servers=self.KAFKA_BROKER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        self.file_positions = {}
        self.logger = get_logger("tpot-log")
    
    def on_modified(self, event): # observer a self verince overwrite etti
        if not event.is_directory and event.src_path.endswith('.log'):
            self.process_log(event.src_path)

    def process_log(self, file_path): 
        current_position = self.file_positions.get(file_path, 0)

        try:
            with open(file_path, 'r') as file:
                file.seek(current_position)
                new_lines = file.readlines()
                if new_lines:
                    self.logger.info(f"Found {len(new_lines)} new lines in {file_path}")

                for line in new_lines:
                    self.send_to_kafka(line)

                self.file_positions[file_path] = file.tell()

        except Exception as ex:
            self.logger.error(f"Error reading logs from tpot: {ex}")

    def send_to_kafka(self, raw_log):
        try:
            log_data = json.loads(raw_log)

            message = {
                'command':log_data.get('payload', ''),
                'source_ip':log_data.get('src_ip', 'unknown'),
                'session_id':f"Tpot_{log_data.get('session_id','default')}"
            }
            self.producer.send_message(self.TOPIC, message=message)
            self.logger.info(f"Log send to kafka: {message['command']}")

        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON: {raw_log}")
        except Exception as ex:
            self.logger.error(f"Error sending logs to kafka: {ex}")

    def start(self):
        observer = Observer()
        observer.schedule(self, path=self.LOG_DIR, recursive=True)
        observer.start()

        self.logger.info(f"Tpot is listening to logs: {self.LOG_DIR}")
        self.logger.info(f"Kafka topic: {self.TOPIC} @ {self.KAFKA_BROKER}")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__ == "__main__":

    event_handler = TpotLogHandler()
    event_handler.start()