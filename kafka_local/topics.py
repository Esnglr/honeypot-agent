"""
Kafka topic definitions for the Honeypot project.
Keeping all topic names in one place ensures consistency across producers and consumers.
"""

# Topic for raw attacker commands captured from the honeypot
# saf saldirgan komutlari burada tutuluyor tpot to kafka buraya gonderi yapiyor data set olusturmak icin uygun  
ATTACKER_COMMANDS = "attacker.commands"

# Topic for tasks created by the MasterAgent and assigned to other agents
# masterdan gelen tum gorevler burda tutuluyor
MASTER_TASKS = "master.tasks"

# Topic for filesystem tasks
# master agent filesystem icin kategorize edilmis gorevlei buraya gonderiyor filesystem consumer burayi dinliyor
FS_TASKS = "filesystem.tasks"

# Topic for wget command tasks
#master agent wget spesifik gorevleri buraya gonderiyor wget consumer burayi dinliyor
WGET_TASKS = "wget.tasks"

# Topic for results produced by agents after completing tasks
# sonuclar buraya gonderilicek success , failure veya suspended gibi
AGENT_RESULTS = "agent.results"

# Topic for security alerts (e.g., IP block, suspicious activity)
# Dashboard burayi dinliycek agent mesaj buraya gondericek tehlike
SECURITY_ALERTS = "security.alerts"
