import sys
import inspect
import logging
import json
from transformers import pipeline
import importlib
from pathlib import Path
from collections import defaultdict
from kafka.kafka_consumer import KafkaConsumer
from kafka.kafka_producer import KafkaProducer
from kafka.topics import ATTACKER_COMMANDS, MASTER_TASKS
from utils.id_generator import generate_task_id
from utils.logger import get_logger
#diger agentlarin sagligi bu agent tarafindan kontrol edilecek
#logging kismiyla ilgilenmeyi unutma
#import pytest ve from unittest.mock import MagicMock arastir

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


class MasterAgent:

    def __init__(self, agent_dir="agents"):
        MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"
        pipe = pipeline("text-generation", model=MODEL_NAME)
        
        self.memory = {
            "fs_initialized": False
        }

        self.logger = get_logger("MasterAgent")
        self.consumer = KafkaConsumer(
            topic=ATTACKER_COMMANDS,
            bootstrap_servers="localhost:9092",
            group_id="master_agent_group"
        )
        self.producer = KafkaProducer(bootstrap_servers="localhost:9092")

        self.agents = {}
        self.load_agents(agent_dir)

        self.category_mapping = defaultdict(list)
        for agent_name, agent_obj in self.agents.items():
            for category in agent_obj.get_tool_names():
                self.category_mapping[category].append(agent_name)

        if not self.category_mapping.get("file_download"):
            self.category_mapping["file_download"] = ["wget", "filesystem"]
        
        if not self.category_mapping.get("filesystem"):
            self.category_mapping["filesystem"] = ["filesystem"]


    def __del__(self):
        """Cleanup on destruction"""
        try:
            if hasattr(self, 'producer'):
                self.producer.close()
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")


    def process_command(self, command_msg: dict):
        """Processes the attacker's commands and assigns tasks"""
        self.logger.info(f"Processing command from {command_msg.get('source_ip')}: {command_msg.get('command')}")

        parsed_command = command_msg.get("command", "").lower()
        if "wget" in parsed_command:
            task_id = generate_task_id()
            parts = parsed_command.split()
            url = None
            try:
                url_index = parts.index("wget") + 1
                url = parts[url_index]
            except (ValueError, IndexError):
                url = None
            
            task = {
                "agent" : "wget",
                "task_id" : task_id,
                "action" : "run",
                "url" : url,
                "original_command" : command_msg.get("command"),
                "session_id" : command_msg.get("session_id")
            }
            self.logger.info(f"Assigning task to AiInteractorWget: {task}")
            self.producer.send_message(MASTER_TASKS, task)
        else:
            self.logger.info("No matching task for command. Ignoring.")


    def load_agents(self, agent_dir):
        for module_file in Path(agent_dir).glob("*.py"): #module_file: agents/file_system_agent.py
            if module_file.name.startswith("_"):
                continue
            
            module_name = f"{agent_dir}.{module_file.stem}"#module_file.stem: file_system_agent
            try:
                module = importlib.import_module(module_name)
                # Find all classes in the module that end with 'Agent'
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and name.endswith("Agent"):
                        agent_name = module_file.stem.replace("_agent", "")
                        self.agents[agent_name] = obj()  # Instantiate the class
                        logging.info(f"Loaded agent: {agent_name} ({name})")

            except ImportError as e:
                logging.error(f"Failed to load agent {module_name}: {e}")


    def send_agent_event(self, event_type: str, payload: Dict[str, Any]):
        """Standardized event sender"""
        message = {
            "event_id": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "event_type": event_type,
            "source": "master_agent",
            "payload": payload
        }
        
        try:
            self.producer.produce(
                topic="agent_events",
                value=message,
                key=payload.get("agent", "").encode('utf-8')
            )
        except Exception as e:
            self.logger.error(f"Failed to send {event_type} event: {e}")


    def categorize_command(self, command):
        prompt = f"""
        You are a Linux command parser. Given an input string, return a JSON object that includes:
        - the base command,
        - any flags (e.g. -x, --help),
        - arguments,
        - and a category (choose from: {list(self.category_mapping.keys())})
        
        Examples:
        1. Input: "nmap -sS -A 192.168.1.1"
        Output: {"command": "nmap", "flags": ["-sS", "-A"], "arguments": ["192.168.1.1"], "category": "network_scanning"}

        2. Input: "tar -xzvf backup.tar.gz"
        Output: {"command": "tar", "flags": ["-x", "-z", "-v", "-f"], "arguments": ["backup.tar.gz"], "category": "file_compression"}

        Now parse: "{command}"
        """
    
        output = self.pipe(prompt, max_length=200, temperature=0.1)
        
        try:
            json_str = output[0]['generated_text'].split("Output:")[-1].strip()
            logging.info("Categorization is succeded.")
            return json.loads(json_str)
        except Exception as e:
            logging.error(f"Command categorization failed: {str(e)}")
            return {"error": str(e)}


    def handle_ambiguous_command(self, attacker_input: str) -> Dict[str, Any]:
        self.logger.info("MasterAgent started listening for attacker commands...")
        self.consumer.listen_forever(self.process_command)
        
        # Initialize Kafka message tracking
        kafka_messages = []
        
        try:
            # Send initial received command event
            self.producer.produce(
                topic="agent_commands",
                value={
                    "type": "command_received",
                    "input": attacker_input,
                    "timestamp": int(time.time()*1000)
                }
            )

            prompt = f"""
            You are an AI orchestrator that routes attacker commands to the correct agents.

            Here are the available agents and their capabilities:
            {self._get_agent_descriptions()}

            The attacker ran: {attacker_input}

            Return a list of actions to take in the format:
            "deploy <agent> <action>"

            Examples:
            - deploy filesystem_agent create_file
            - deploy wget_agent download_url

            Now respond with appropriate deployments.
            """


            agent_plan_output = self.pipe(prompt, max_new_tokens=100, temperature=0.2)[0]['generated_text'].strip()
            agent_plan = self._parse_agent_plan(agent_plan_output)

            logging.info(f"AI agent plan:\n{agent_plan_output}")
        
            # Send planning complete event
            self.producer.produce(
                topic="agent_commands",
                value={
                    "type": "plan_created",
                    "plan": agent_plan_output,
                    "timestamp": int(time.time()*1000)
                }
            )

            categorized_input = self.categorize_command(attacker_input)
            if "error" in categorized_input:
                logging.info("Error in categorization.")
                self.producer.produce(
                    topic="agent_errors",
                    value={
                        "type": "categorization_failed",
                        "error": categorized_input["error"],
                        "input": attacker_input,
                        "timestamp": int(time.time()*1000)
                    }
                )
                return {"status": "error", "message": "Failed to categorize command."}

            command = categorized_input.get("command")
            flags = categorized_input.get("flags")
            arguments = categorized_input.get("arguments")
            category = categorized_input.get("category")

            results = []
            for agent_name, action in agent_plan:
                agent = self.agents.get(agent_name)
                if agent:
                    try:
                        if not self.memory["fs_initialized"]:
                            fs_agents = self.category_mapping.get("filesystem", [])
                            if fs_agents:
                                fs_agent = self.agents.get(fs_agents[0])
                                if fs_agent:
                                    fs_result = fs_agent.run()
                                    results.append((fs_agents[0], fs_result))
                                    self.memory["fs_initialized"]= True
                                    logging.info("File system is initialized by FileAgent.")
                                    
                                    # Send FS init event
                                    self.producer.produce(
                                        topic="agent_events",
                                        value={
                                            "type": "filesystem_initialized",
                                            "agent": fs_agents[0],
                                            "timestamp": int(time.time()*1000)
                                        }
                                    )

                                else:
                                    logging.warning("FileAgent is not found. Cannot initialize file system.")
                            else:
                                logging.warning("No agents registered for filesystem category.")

                        result = agent.run(
                            command=command,
                            flags=flags,
                            arguments=arguments,
                            category=category,
                            action=action
                        )
                        results.append((agent_name, result))
                        
                        # Send success event
                        self.producer.produce(
                            topic="agent_actions",
                            value={
                                "type": "action_completed",
                                "agent": agent_name,
                                "action": action,
                                "result": str(result),
                                "timestamp": int(time.time()*1000)
                            }
                        )

                    except Exception as e:
                        results.append((agent_name, f"error: {str(e)}"))

                        # Send error event
                        self.producer.produce(
                            topic="agent_errors",
                            value={
                                "type": "action_failed",
                                "agent": agent_name,
                                "action": action,
                                "error": error_msg,
                                "timestamp": int(time.time()*1000)
                            }
                        )
            
            self.producer.flushing()

            return {
                "status": "success",
                "agent_plan": agent_plan_output,
                "results": results
            }

        except Exception as ex:
            self.producer.produce(
                topic="agent_errors",
                value={
                    "type": "processing_failed",
                    "input": attacker_input,
                    "error": str(e),
                    "timestamp": int(time.time()*1000)
                }
            )
            self.producer.flushing()
            raise     

    def _parse_agent_plan(self, output):
        actions = []
        for line in output.strip().splitlines():
            if line.lower().startswith("deploy"):
                parts = line.split()
                if len(parts) >= 3:
                    _, agent_name, action = parts[:3]
                    actions.append((agent_name, action))
        return actions

    def _get_agent_descriptions(self):
        desc = ""
        for name, agent in self.agents.items():
            tools = ", ".join(agent.get_tool_names())
            desc += f"- {name}: handles [{tools}]\n"
        return desc


    def handle_file_download(self, url: str, outfile: str=None, ip: str=None, user: str="unknown"):
        transaction_id = str(uuid.uuis64())

        try:
            self.producer.send_agent_event(
                agent_name="master",
                event_type="download_coordination_start",
                payload={
                    "transaction_id": transaction_id,
                    "url": url,
                    "target_file": outfile,
                    "source_ip": ip,
                    "user": user
                }
            )

            wget_agent = self.agents.get("wget")
            if not wget_agent:
                raise ValueError("Wget agent is not available.")

            download_result = wget_agent.file_metadata(
                url=url,
                outfile=outfile,
                quiet=False
            )
            
            file_agent = next((a for a in self.agents.values() 
                            if "filesystem" in a.get_tool_names()), None)
            
            if not file_agent:
                raise ValueError("Filesystem agent not available")

            creation_result = file_agent.create_file(
                filename=download_result['filename'],
                file_type=download_result['file_type'],
                size=download_result['size'],
                content_type=download_result['content_type'],
                source_url=url
            )

            self.producer.send_agent_event(
                agent_name="master",
                event_type="download_coordination_complete",
                payload={
                    "transaction_id": transaction_id,
                    "status": "success",
                    "metrics": {
                        "duration_ms": int((time.time() - start_time) * 1000),
                        "file_size": download_result['size']
                    }
                }
            )

            return{
                "status": "success",
                "download": download_result,
                "file_creation": creation_result
            }

        except Exception as e:
            self.producer.send_agent_event(
                agent_name="master",
                event_type="download_coordination_failed",
                payload={
                    "transaction_id": transaction_id,
                    "error": str(e),
                    "stage": "coordination"
                }
            )
            raise


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logging.warning("Parameters are not given properly")
        sys.exit(1)

    attacker_input = " ".join(sys.argv[1:])
    try:
        master = MasterAgent()
        result = master.handle_ambiguous_command(attacker_input)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print("Did not even started properly.")
        logging.error(f"Unhandled error: {str(e)}")
        sys.exit(1)