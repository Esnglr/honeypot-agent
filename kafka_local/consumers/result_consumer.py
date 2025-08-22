from kafka_local import topics        
from kafka_local.kafka_consumer import KafkaConsumer
#sonrasinda sekillenebilecek bir consumer mantigi olabilir

class Result():
    def __init__(self):
        results_consumer = KafkaConsumer(
            topic=topics.AGENT_RESULTS, 
            bootstrap_servers="localhost:9092",
            group_id=Id.generate_group_id()
        )
        results_thread = threading.Thread(
            target=lambda: results_consumer.listen_forever(self.handle_agent_result),
            daemon=True
        )
        results_thread.start()