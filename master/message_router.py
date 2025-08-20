from kafka_local.kafka_consumer import KafkaConsumer
from kafka_local.kafka_producer import KafkaProducer
from kafka_local import topics
from utils.logger import get_logger
from utils.id_generator import Id

class MessageRouter:
    def __init__(self, bootstrap_servers="localhost:9092"):
        self.consumer = KafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            topic=topics.MASTER_TASKS,
            group_id=Id.generate_group_id()
        )
        self.producer = KafkaProducer(bootstrap_servers=bootstrap_servers)
        self.running = True
        self.logger = get_logger("message-router")

    def route_task(self, task:dict):
        target_agent = task.get("target_agent")
        if not target_agent:
            self.logger.warning(f"Task missing target_agent: {task}")
            return
        
        agent_topic_map = {
            "ai_interactor": topics.WGET_TASKS,
            "file_system_agent": topics.FS_TASKS
        }
        topic = agent_topic_map.get(target_agent)
        if not topic:
            self.logger.error(f"Unknown target_agent '{target_agent}' in task {task.get('task_id')}")
            return
        
        self.logger.info(f"Routing task {task.get('task_id')} to topic {topic}")
        self.producer.send_message(topic, task)


    def route_result(self, result: dict):
        self.logger.info(f"Received result: {result}")


    def run(self):
        self.logger.info("MessageRouter started.")
        try:
            for message in self.consumer:
                msg = message.value

                if "target_agent" in msg:
                    self.route_task(msg)
                elif "result_data" in msg:
                    self.route_result(msg)
                else:
                    self.logger.warning(f"Unknown message type: {msg}")
        except Exception as ex:
            self.logger.error(f"MessageRouter error: {ex}")
        finally:
            self.consumer.close()
            self.producer.flush()
            self.logger.info("MessageRouter shutdown complete")


if __name__ == "__main__":
    router = MessageRouter()
    router.run()