import sys
import inspect
import logging
import json
from transformers import pipeline
import importlib
from pathlib import Path
from collections import defaultdict
from kafka_local.kafka_consumer import KafkaConsumer
from kafka_local.kafka_producer import KafkaProducer
from kafka_local.topics import ATTACKER_COMMANDS, MASTER_TASKS
from utils.id_generator import Id
from utils.logger import get_logger
from master.task_manager import TaskManager
from master.message_router import MessageRouter
import threading
import time
from typing import Dict, Any
#import pytest ve from unittest.mock import MagicMock arastir


class MasterAgent:

    def __init__(self, agent_dir="agents"):
        self._initialize_filesystem()

        MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"
        self.pipe = pipeline("text-generation", model=MODEL_NAME)
        
        self.task_manager = TaskManager()
        self.message_router = MessageRouter(bootstrap_servers=["localhost:9092"])


        self.memory = {
            "fs_initialized": False
        }
        self.memory_lock = threading.lock()

        self.logger = get_logger("MasterAgent")
        self.consumer = KafkaConsumer(
            topic=ATTACKER_COMMANDS,
            bootstrap_servers="localhost:9092",
            group_id=Id.generate_group_id()
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

        router_thread = threading.Thread(target=self.message_router.run, daemon=True)
        router_thread.start()
        listener_thread = threading.Thread(
            target=lambda: self.consumer.listen_forever(self.process_command),
            daemon=True
        )
        listener_thread.start()

        results_consumer = KafkaConsumer(
            topic=AGENT_RESULTS,  # Make sure to import this
            bootstrap_servers="localhost:9092",
            group_id=Id.generate_group_id()
        )
        results_thread = threading.Thread(
            target=lambda: results_consumer.listen_forever(self.handle_agent_result),
            daemon=True
        )
        results_thread.start()


    def __del__(self):
        """Cleanup on destruction"""
        try:
            if hasattr(self, 'producer'):
                self.producer.close()
            if hasattr(self, 'consumer'):
                self.consumer.close()
        except Exception as ex:
            self.logger.error(f"Cleanup error: {ex}")


    def _initialize_filesystem(self):
        fs_agent = self.category_mapping.get("filesystem", None)
        if not fs_agent:
            self.logger.warning("No filesystem agent is available")
            raise

        task = self.task_manager.create_task(
            command={
                "raw": "Initialize filesystem",
                "parsed":{
                    "command": "init_fs", # if task['command']['parsed']['command'] == 'init_fs': prompt="" -> in fs consumer
                    "flags": [],
                    "arguments": [],
                    "category": "filesystem",
                    "action": "initialize"
                },
                "session_id": "system"
            },
            target_agent=fs_agent
        )
        self.message_router.route_task(task)
        self.logger.info(f"Filesyste, initialization task created: {task['task_id']}")


    def process_command(self, command_msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle ONE attacker command message that arrives from Kafka.

        Expected command_msg shape (at minimum):
        {
            "command": "...raw attacker command...",
            "session_id": "...",            # optional
            "source_ip": "1.2.3.4",         # optional
        }
        """
        attacker_input = (command_msg or {}).get("command", "")
        session_id = (command_msg or {}).get("session_id", "unknown")

        # Track per-call results
        results = []
        agent_tasks: Dict[str, Dict[str, Any]] = {}

        # 1) Announce command receipt
        try:
            self.producer.send_message(
                "agent_commands",
                {
                    "type": "command_received",
                    "input": attacker_input,
                    "session_id": session_id,
                    "timestamp": int(time.time() * 1000),
                },
            )
            self.producer.flush()
        except Exception as _:
            # Don't fail the run because of telemetry
            pass

        try:
            # 2) Build plan with LLM
            prompt = f"""
            You are an AI orchestrator that routes attacker commands to the correct agents.

            Here are the available agents and their capabilities:
            {self._get_agent_descriptions()}

            The attacker ran: {attacker_input}

            Return a list of actions to take in the format:
            "deploy <agent> <action>"
            """
            agent_plan_output = self.pipe(prompt, max_new_tokens=100, temperature=0.2)[0]["generated_text"].strip()
            agent_plan = self._parse_agent_plan(agent_plan_output)
            self.logger.info(f"AI agent plan:\n{agent_plan_output}")

            self.producer.send_message(
                "agent_commands",
                {
                    "type": "plan_created",
                    "plan": agent_plan_output,
                    "timestamp": int(time.time() * 1000),
                },
            )
            self.producer.flush()

            # 3) Categorize the command
            categorized_input = self.categorize_command(attacker_input)
            if "error" in categorized_input:
                self.logger.info("Error in categorization.")
                self.producer.send_message(
                    "agent_errors",
                    {
                        "type": "categorization_failed",
                        "error": categorized_input["error"],
                        "input": attacker_input,
                        "timestamp": int(time.time() * 1000),
                    },
                )
                self.producer.flush()
                return {"status": "error", "message": "Failed to categorize command."}


            command = categorized_input.get("command")
            flags = categorized_input.get("flags")
            arguments = categorized_input.get("arguments")
            category = categorized_input.get("category")

            with self.memory_lock:
                if not self.memory.get("fs_initialized", False):
                    self._initialize_filesystem()
            
            task_ids = []
            for agent_name, action in agent_plan:
                if agent_name not in self.agents:
                    self.logger.warning(f"Agent '{agent_name}' not found, skipping.")
                    continue
                task = self.task_manager.create_task(
                    command={
                        "raw":attacker_input,
                        "parsed":{
                            "command": command,
                            "flags": flags,
                            "arguments": arguments,
                            "category": category,
                            "action": action
                        },
                        "session_id": session_id
                    },
                    target_agent=agent_name
                )
                self.message_router.route_task(task)
                task_ids.append(task["task_id"])
            return{
                "status": "success",
                "agent_plan": agent_plan_output,
                "task_ids": task_ids
            }
        except Exception as ex:
            self.logger.error(f"Command procesing failed: {str(ex)}")
            try:
                self.producer.send_message(
                    "agent_errors",
                    {
                        "type": "processing_failed",
                        "input": attacker_input,
                        "error": str(ex),
                        "timestamp": int(time.time()*1000)
                    }
                )
            finally:
                self.producer.flush()
                return {"status": "error", "message": str(ex)}



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
                        self.logger.info(f"Loaded agent: {agent_name} ({name})")

            except ImportError as e:
                self.logger.error(f"Failed to load agent {module_name}: {e}")
                raise


    def send_agent_event(self, event_type: str, payload: Dict[str, Any]):
        """Standardized event sender"""
        message = {
            "event_id": Id.generate_short_id(),
            "timestamp": int(time.time() * 1000),
            "event_type": event_type,
            "source": "master_agent",
            "payload": payload
        }
        
        try:
            self.producer.send_message(
                topic="agent_events",
                message=message
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
            self.logger.info("Categorization is succeded.")
            return json.loads(json_str)
        except Exception as e:
            self.logger.error(f"Command categorization failed: {str(e)}")
            return {"error": str(e)}


    def handle_agent_result(self, result: dict):
        """Process results from agents"""
        task_id = result.get("task_id")
        if not task_id:
            self.logger.warning(f"Result missing task_id: {result}")
            return
            
        task = self.task_manager.get_task(task_id)
        if not task:
            self.logger.warning(f"Received result for unknown task: {task_id}")
            return
            
        # Update task status
        new_status = "completed" if result.get("success") else "failed"
        self.task_manager.update_task_status(task_id, new_status)
        
        # special case
        if task["target_agent"] in self.category_mapping["filesystem"] and task["command"]["parsed"].get("action") == "initialize" and new_status == "completed":
            with self.memory_lock:
                self.memory["fs_initialized"] = True

        # Send event
        self.send_agent_event(
            event_type="task_result_received",
            payload={
                "task_id": task_id,
                "status": new_status,
                "agent": task["target_agent"],
                "result": result.get("result_data", "")
            }
        )


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
        transaction_id = Id.generate_short_id()
        start_time = time.time()

        try:
            self.send_agent_event(
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

            self.send_agent_event(
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
            self.send_agent_event(
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
        self.logger.warning("Parameters are not given properly")
        sys.exit(1)

    attacker_input = " ".join(sys.argv[1:])
    
    master = MasterAgent()
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        master.logger.info("Shutting down MasterAgent")
        sys.exit(0)