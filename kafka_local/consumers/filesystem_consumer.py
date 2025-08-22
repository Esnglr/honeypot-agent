from kafka_local.kafka_consumer import KafkaConsumer
from kafka_local.kafka_producer import KafkaProducer
import json
from utils.logger import get_logger
from utils.id_generator import Id
from agents.MPT_file_system_creation_agent_debuged import AutonomousFileAgent
from kafka_local import topics
from datetime import datetime

class FileSystemConsumer:
    def __init__(self, bootstrap_servers="localhost:9092"):
        self.logger = get_logger("fs-consumer")
        self.consumer = KafkaConsumer(
            topics.FS_TASKS,
            bootstrap_servers=bootstrap_servers,
            group_id=Id.generate_group_id()
        )
        self.agent = AutonomousFileAgent()

    def start(self):
        self.logger.info("FileSytemConsumer started, waiting for tasks...")
        for message in self.consumer:
            
            if message.value is None:
                self.logger.warning("Received None message, skipping...")
                continue

            try:
                task = message.value
                self.logger.info(f"Received task: {task}")
                
                #master agentin gonderdigi formati iyice test et ondan sonra burayi duzenlersin .get() kullanabilicek misin emin ol 
                #parsed = task["command"]["parsed"]
                #task_id = task["task_id"]

                try:
                    command = task['action']
                    #command = parsed["command"]
                    if command == "delete_file":
                        # bu kisimlari gelistirmeyi unutma son dokunuslar olarak
                        prompt = ""
                        file_path = task["file_path"]
                        print("deleting file")
                        self.agent.run(prompt)
                    elif command == "":
                        self.agent
                    else:
                        self.logger.warning(f"Unknown command: {command}")
                        raise
                    # burda task id zaten producerdan gelicek id jenere etme
                    task_id = Id.generate_task_id()
                        
                except Exception as ex:
                    self.logger.error(f"Error handling file system task: {ex}")
                
            #bu hala hata veriyor catch etmiyor
            except KeyboardInterrupt:
                self.logger.info("Shutting down gracefully...")

            except Exception as ex:
                self.logger.error(f"Error processing message: {ex}")
            
            finally:
                self.consumer.close()
                self.producer.close()


if __name__ == "__main__":
    consumer = FileSystemConsumer()
    consumer.start()