from kafka_local.kafka_consumer import KafkaConsumer
from kafka_local.kafka_producer import KafkaProducer
import json
from utils.logger import get_logger
from utils.id_generator import Id
from commands.wget import CommandWget
from kafka_local import topics
from datetime import datetime
# KeyboardInterrupt i yakalayamiyorum

class WgetConsumer:
    def __init__(self, bootstrap_servers="localhost:9092"):
        self.logger = get_logger("wget-consumer")

        self.consumer = KafkaConsumer(
            topics.AGENT_TASKS_WGET,
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            group_id=Id.generate_group_id(),
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
        )
        self.agent = CommandWget()

    
    def start(self):
        self.logger.info("WgetConsumer started, waiting for tasks...")
        for message in self.consumer:
            try:
                task = message.value
                self.logger.info(f"Received task: {task}")

                command = task.get("command")
                parsed = command.get("parsed")
                action = parsed.get("action")
                task_id = task.get("task_id")
                #parsed = task["command"]["parsed"]
                #task_id = task["task_id"]

                try:
                    #command = parsed["command"]
                    if action == "run":
                        try:
                            self.agent.start(**task)
                        except Exception as ex:
                            self.logger.error(f"Error starting wget agent: {ex}")
                            self.send_result(task_id, "failed", error=str(ex))
                    else:
                        self.logger.warning(f"Unknown action '{action}' for WgetConsumer")
                
                except Exception as ex:
                    self.logger.error(f"Error handling wget task: {ex}")
                    self.send_result(task_id, "failed", error=str(ex))

            except Exception as ex:
                self.logger.error(f"Error processing message: {ex}")
                self.send_result(task_id, "failed", error=str(ex))


    def send_result(self, task_id, status, result=None, error=None):
        message = {
            "task_id": task_id,
            "status": status,
            "timestamp":datetime.now().strftime("%-d.%-m.%Y %H.%M") ,
            "result_data": result,
            "error": error
        }
        self.producer.send_message(topics.AGENT_RESULTS, message)
        self.producer.flush()

if __name__ == "__main__":
    consumer = WgetConsumer()
    consumer.start()