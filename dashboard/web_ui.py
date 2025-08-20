from flask import Flask, render_template, request, redirect, url_for, flash
from dashboard.consumer_alerts import AlertConsumer
from kafka_local.kafka_producer import KafkaProducer
import json
import threading

BROKERS = ["localhost:9092"]

app = Flask(__name__)
app.secret_key = "PDiuec398-JPe28-&@l[]"
alert_consumer = AlertConsumer(BROKERS)


producer = KafkaProducer(
    bootstrap_servers=BROKERS,
)

AGENTS= {
    "FileSystemAgent":"running",
    "AiInteractorWget":"stopped"
}

def start_consumers():
    alert_consumer._consume_actions()
    alert_consumer._consume_alerts()

threading.Thread(target=start_consumers, daemon=True).start()



@app.route("/")
def index():
    alerts = alert_consumer.get_alerts() #returns list
    actions = alert_consumer.get_actions()
    return render_template("index.html", alerts=alerts, actions=actions, agents=AGENTS)

@app.route("/ban_ip", methods=["POST"])
def ban_ip():
    ip = request.form.get("ip")
    if ip:
        msg = {"action":"ban_ip", "ip":ip}
        alert_consumer.add_pending_action("ban ip", ip)
        topic =  "requests"
        producer.send_message(topic,msg)
        producer.flush()
        flash(f"Ban request is sent for IP {ip}")
    return redirect(url_for("index"))

@app.route("/reset", methods=["POST"])
def reset():
    msg ={"action": "reset"}
    alert_consumer.add_pending_action("reset")
    topic="requests"
    producer.send_message(topic,msg)
    producer.flush()
    flash("Reset request is sent")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)