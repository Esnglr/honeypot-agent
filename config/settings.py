# config/settings.py

# Kafka connection settings
KAFKA_BOOTSTRAP_SERVERS = ["localhost:9092"]

# Kafka topic names
TOPICS = {
    "ATTACKER_COMMANDS": "attacker.commands",
    "MASTER_TASKS": "master.tasks",
    "AGENT_TASKS_WGET": "agent.tasks.wget",
    "AGENT_TASKS_FS": "agent.tasks.filesystem",
    "AGENT_RESULTS": "agent.results",
}

# Agent-specific configs
AGENTS = {
    "COMMAND_CAPTURE_AGENT": {
        "session_timeout_seconds": 3600,
    },
    "MASTER_AGENT": {
        "task_timeout_seconds": 300,
    },
    "FILE_SYSTEM_AGENT": {
        "base_path": "/tmp/honeypot_files",
    },
    "AI_INTERACTOR_WGET": {
        "download_path": "/tmp/honeypot_downloads",
    },
}

# Logging config file path
LOGGING_CONFIG_FILE = "config/logging.conf"
