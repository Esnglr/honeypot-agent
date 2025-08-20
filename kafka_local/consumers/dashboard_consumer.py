from kafka_local.kafka_consumer import KafkaConsumer
from kafka_local.kafka_producer import KafkaProducer
import json
from utils.logger import get_logger
from utils.id_generator import Id
import subprocess
from datetime import datetime

class DashboardConsumer:
    def __init__(self, bootstrap_servers="localhost:9092"):
        self.logger = get_logger("dashboard-consumer")
        self.consumer = KafkaConsumer(
            'requests',
            bootstrap_servers=bootstrap_servers,
            group_id=Id.generate_group_id()
        )
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers
        )
        self.ip = None

    def start(self):
        self.logger.info("Dashboard-Consumer started, waiting for tasks...")
        for msg in self.consumer:
            command = msg.value
            self.process_command(command)

    def process_command(self,command):
        action = command.get("action")
        if action == "ban_ip":
            self.ip = command.get("ip")
            self.logger.info(f"Banning IP: {self.ip}")
            self.ban_ip()
        elif action == "reset_honeypot":
            self.reset()
        else:
            self.logger.warning(f"Unknown command: {command}")

    def ban_ip(self):
        try:
            subprocess.run(["sudo", "iptables", "-A", "INPUT", "-s", self.ip, "-j", "DROP"], check=True)
            self.send_alert({"action": "ban_ip", "ip": self.ip, "status": "success"})
            self.logger.info(f"Banned the IP {self.ip}")
        except subprocess.CalledProcessError:
            self.logger.error(f"Failed to block IP: {self.ip}")
            self.send_alert({"action": "ban_ip", "ip": self.ip, "status": "failed"})

    def reset(self):
        try:
            subprocess.run(["sudo", "iptables", "-F"], check=True)
            self.logger.info("Iptables rules reseted.")
            self.send_alert({"action": "reset", "ip":self.ip, "status": "success", "timestamp":datetime.now().strftime("%-d.%-m.%Y %H.%M")})
        except subprocess.CalledProcessError:
            self.send_alert({"action": "reset", "ip":self.ip, "status": "failed", "timestamp":datetime.now().strftime("%-d.%-m.%Y %H.%M")})
            self.logger.error("Failed to reset iptables")
   
    def send_alert(self,alert):
        self.producer.send_message("security.actions", alert)
        self.logger.info("Sent back alert.")
        self.producer.flush()

if __name__ == "__main__":
    consumer = DashboardConsumer()
    consumer.start()