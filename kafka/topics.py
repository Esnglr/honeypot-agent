"""
Kafka topic definitions for the Honeypot project.
Keeping all topic names in one place ensures consistency across producers and consumers.
"""

# Topic for raw attacker commands captured from the honeypot
ATTACKER_COMMANDS = "attacker.commands"

# Topic for tasks created by the MasterAgent and assigned to other agents
MASTER_TASKS = "master.tasks"

# Topic for results produced by agents after completing tasks
AGENT_RESULTS = "agent.results"

# Topic for security alerts (e.g., IP block, suspicious activity)
SECURITY_ALERTS = "security.alerts"
