from kafka_local.kafka_consumer import KafkaConsumer
from kafka_local.kafka_producer import KafkaProducer
from utils.logger import get_logger
import threading
import json
from datetime import datetime
from uuid import uuid4
#requestler databasede de saklanabilir suan sadece kafka kullandim o sekilde ilerliyoruz diye

class AlertConsumer:
    def __init__(self, brokers, topic="security.alerts"):
        self.alerts_consumer = KafkaConsumer(
            topic,
            bootstrap_servers=brokers,
            group_id=f"webui-{uuid4()}",
            auto_offset_reset='earliest'
        )
        self.actions_consumer = KafkaConsumer(
            'security.actions',
            bootstrap_servers=brokers,
            group_id=f"webui-{uuid4()}",
            auto_offset_reset='earliest' 
        )
        self.producer = KafkaProducer(bootstrap_servers=self.alerts_consumer.bootstrap_servers)
        
        self.logger = get_logger("alert-consumer")
        self.alerts = []
        self.actions = []
        self.banned_ips = set() #listeden daha hizliymis O(1)
        self.lock = threading.Lock()
        


    def _consume_alerts(self):
        try:
            for msg in self.alerts_consumer:
                with self.lock:
                    self.alerts.insert(0, msg.value)
                    if len(self.alerts) > 100:
                        self.alerts.pop()

        except StopIteration:
            print("Consumer shutdown")
        except Exception as e:
            print(f"Consumer error: {str(e)}")
            

    def _consume_actions(self):
        try:
            for msg in self.actions_consumer:
                action_data = msg.value
                with self.lock:
                    self.actions.insert(0, action_data)
                    if len(self.actions) > 100:
                        self.actions.pop()
                    if (action_data.get('action')=='ban_ip' and
                        action_data.get('status')=='completed' and
                        action_data.get('ip')):
                        self.banned_ips.add(action_data['ip'])
                        self.logger.info(f"IP banned and added to blacklist: {action_data['ip']}")
        except Exception as e:
            print(f"Actions consumer error: {str(e)}")


    def get_alerts(self):
        with self.lock:
            return list(self.alerts)

    def get_actions(self):
        with self.lock:
            return list(self.actions)

    def get_banned_ips(self):
        with self.lock:
            return list(self.banned_ips)

    def is_ip_banned(self, ip):
        with self.lock:
            return ip in self.banned_ips

    def add_pending_action(self, action_type, ip=None):
        msg = {
            "action": action_type,
            "ip":ip,
            "status":"pending",
            "timestamp":datetime.now().strftime("%-d.%-m.%Y %H.%M")
        }

        self.producer.send_message('security.actions', msg)
        self.producer.flush()