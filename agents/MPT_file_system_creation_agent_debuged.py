from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from pydantic import BaseModel, Field
import os
import logging
import base64
from datetime import timedelta
from typing import Optional, Union, Dict, Any
import subprocess
import pwd
import grp
from faker import Faker
import threading
import time
from functools import partial
import json
from duckduckgo_search import DDGS
import random
import shlex
from typing import Callable, List, Optional
import transformers
from kafka.kafka_producer import KafkaProducer
from kafka.kafka_consumer import KafkaConsumer
#logging mantigi degistirilecek
print(DDGS().text("test", max_results=1))

class Tool:
    def __init__(self, name:str, func: Callable, description: str, parameters: dict):
        self.name = name
        self.func = func
        self.description = description
        self.parameters = parameters

    def execute(self, **kwargs) -> Any:
        return self.func(**kwargs)
    
    def to_dict(self) -> dict:
        """Convert tool to OpenAI-compatible format"""
        required = []
        for param, config in self.parameters.items():
            if not isinstance(config, dict):
                continue
            if not config.get("optional", False):
                required.append(param)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": required
                }
            }
        }

    def get_tool_schemas_for_prompt(self) -> str:
        lines = [
            f"{self.name}: {self.description}",
            "Parameters:"
        ]
        
        for param, config in self.parameters.items():
            # Extract parameter details
            param_type = config.get("type", "string")
            description = config.get("description", "")
            optional = config.get("optional", False)
            enum_values = config.get("enum", None)
            
            # Format the parameter line
            param_line = f"  - {param} ({param_type}, {'optional' if optional else 'required'}): {description}"
            
            # Add enum options if available
            if enum_values:
                param_line += f" (Options: {enum_values})"
            
            lines.append(param_line)
        
        return "\n".join(lines)



class FileSystemAgentActions(BaseModel):
    """Model for tracking individual agent actions"""
    function_name: str = Field(..., description="Name of the function called")
    arguments: Dict[str, Any] = Field(..., description="Arguments passed to the function")
    result: str = Field(..., description="Result of the operation")
    success: bool = Field(..., description="Whether the operation succeeded")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of action")



class AutonomousFileAgent:
    def __init__(self):
        # Initialize MPT-7B-Instruct
        self.model_name = "mistralai/Mistral-7B-Instruct-v0.2"

        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            trust_remote_code=True
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            torch_dtype=torch.float32  # Or float16 if using CUDA
        ).to("cpu")

        self.tools = self._initialize_tools()
        self.actions_log = []
        self.tool_dispatch = {tool.name: tool.func for tool in self.tools}
        self.current_task = None
        self.fake = Faker()
        self.kafka_producer = KafkaProducer()
        self.sampling_params = SamplingParams(
            temperature=0.3,
            top_p=0.9,
            max_tokens=100,
            stop=["\n\n"]
        )

        # Kafka Setup
        self.command_consumer = KafkaConsumer(
            'task-assignments',
            bootstrap_servers='localhost:9092',
            group_id='filesystem-agents',
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')))
        
        self.result_producer = KafkaProducer(
            bootstrap_servers='localhost:9092',
            value_serializer=lambda x: json.dumps(x).encode('utf-8'))


    def cleanup(self):
        logging.info("Cleaning up Kafka resources")
        
        if hasattr(self, 'command_consumer'):
            try:
                self.command_consumer.close()
            except Exception as ex:
                logging.error(f"Error closing consumer: {ex}")
    
    if hasattr(self, 'result_producer'):
        try:
            self.result_producer.flush(timeout=5.0)
            self.result_producer.close()
        except Exception as ex:
            logging.error(f"Error closing producer: {ex}")

    def get_all_tool_descriptions(self) -> str:
        """Generates a prompt-friendly list of all available tools."""
        return "\n\n".join(
            tool.get_tool_schemas_for_prompt()
            for tool in self.tools
        )

    def _initialize_tools(self) -> List[Tool]:
        """Initialize all available tools"""
        return [
            Tool(
                name="ddg",
                func=self.ddg,
                description="Search DuckDuckGo for real-time information",
                parameters={
                    "keywords": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results to return", "default": 3, "optional": True}
                }
            ),
            Tool(
                name="create_directory",
                func=self.create_directory,
                description="Creates a directory at the specified path",
                parameters={
                    "dir_path": {"type": "string", "description": "Path of the directory to create"}
                }
            ),
            Tool(
                name="create_file",
                func=self.create_file,
                description="Creates a file with optional content type and backdating",
                parameters={
                    "path": {"type": "string", "description": "Directory path"},
                    "filename": {"type": "string", "description": "File name"},
                    "content_type": {
                        "type": "string", 
                        "description": "Type of content",
                        "enum": ["log", "pgp", "sql", "text", "failed_backup"],
                        "optional": True
                    },
                    "backdate_days": {"type": "integer", "description": "Days to backdate", "optional": True}
                }
            ),
            Tool(
                name="backdate_file",
                func=self.backdate_file,
                description="Backdates a file to appear older than it is. System files is more likely to be older , so keep in mind which file path and filename you are backdating.",
                parameters={
                    "path": {"type": "string", "description": "Path to the file to backdate."},
                    "days": {"type": "integer", "description": "Exact number of days to backdate (optional)."},
                    "min_days": {"type": "integer", "description": "Minimum days for random backdating (default 30)."},
                    "max_days": {"type": "integer", "description": "Maximum days for random backdating (default 800)."}
                }
            ),
            Tool(
                name="create_process",
                func="self.create_process",
                description="Creates a new process with the given command. Make the system realistic , do not exaggerate.",
                parameters={
                    "command": {"type": "string", "description": "Command to execute."}
                }
            ),
            Tool(
                name="create_user",
                func="self.create_user",
                description="Creates a user account with optional parameters. Simulate a real system , how many user most likely to be in a linux file system?",
                parameters={
                    "username": {"type": "string", "description": "Name of the user to create (optional, will generate if not provided)."},
                    "home_dir": {"type": "string", "description": "Home directory path (optional)."},
                    "shell": {"type": "string", "description": "Login shell (default: /bin/bash)."},
                    "system_account": {"type": "boolean", "description": "If True, creates a system account."}
                }
            ),
            Tool(
                name="create_group",
                func="self.create_group",
                description="Creates a group with optional GID.Also you can search for internet for this one for how many groups are usually are there and what are the common names for them?",
                parameters={
                    "group_name": {"type": "string", "description": "Name of the group to create (optional, will generate if not provided)."},
                    "gid": {"type": "integer", "description": "Group ID (optional)."},
                    "system_group": {"type": "boolean", "description": "If True, creates a system group."}
                }
            ),
            Tool(
                name="change_file_owner",
                func="self.change_file_owner",
                description="Changes ownership of a file/directory.",
                parameters={
                    "path": {"type": "string", "description": "Path to the file/directory."},
                    "user": {"type": ["string", "integer"], "description": "User name or ID (optional)."},
                    "group": {"type": ["string", "integer"], "description": "Group name or ID (optional)."}
                }
            ),
            Tool(
                name="generate_password",
                func="self.generate_password",
                description="Generates a random password with customizable complexity. **DO NOT CALL DIRECTLY**—this function is used internally by the system. Only provide parameter suggestions when explicitly asked.",
                parameters={
                    "length": {"type": "integer", "description": "Length of the password (default 10)."},
                    "require_special_chars": {"type": "boolean", "description": "Include special characters (default True)."},
                    "require_upper_case": {"type": "boolean", "description": "Include uppercase letters (default True)."},
                    "require_lower_case": {"type": "boolean", "description": "Include lowercase letters (default True)."},
                    "require_digits": {"type": "boolean", "description": "Include digits (default True)."}
                }
            )
        ]

    def ddg(self, keywords: str, max_results: int = 3) -> list:
        max_retries = 3
        retry_delay = 2

        for _ in range(max_retries):
            try:
                with DDGS() as ddgs:
                    return ddgs.text(keywords, max_results=max_results)
            except Exception as e:
                logging.warning(f"DDG search failed: {e}")
                time.sleep(retry_delay)

        return []


    def generate_username(self) -> str:
        return self.fake.user_name()

    def generate_password(self, length:int=10,
    require_special_chars:Optional[bool]=True,
    require_upper_case:Optional[bool]=True,
    require_lower_case:Optional[bool]=True,
    require_digits:Optional[bool]=True) -> str:
        return self.fake.password(
            length=length,
            special_chars=require_special_chars,
            digits=require_digits,
            upper_case=require_upper_case,
            lower_case=require_lower_case,
        )

    def generate_file_content(self) -> str:
        return self.fake.text()

    def generate_fake_pgp_message(self) -> str:
        # Generate 256 bytes of random binary data, encode as Base64 (like real PGP)
        fake_binary_data = self.fake.binary(length=256)
        fake_base64 = base64.b64encode(fake_binary_data).decode('utf-8')

        # Split into lines (PGP messages often wrap at 64 chars)
        formatted_base64 = '\n'.join([fake_base64[i:i+64] for i in range(0, len(fake_base64), 64)])

        return f"""-----BEGIN PGP MESSAGE-----
            Version: OpenPGP 2.0
            Comment: Created by GPG 2.4.3 (Linux)

            {formatted_base64}
            -----END PGP MESSAGE-----
            """


    def generate_failed_backup(self) -> str:
        return f"""
            === Database Backup {self.fake.date_between(start_date="-3y", end_date="today")} ===
            TABLE users: 12 records dumped.
            \x00\x00ERROR: Connection lost at record 13/50.
            RAW DUMP: {self.fake.uuid4()}
            {self.fake.text()}
            """


    def generate_corrupted_log(self) -> str:
        fake_date = self.fake.date_time_between(start_date="-3y", end_date="now")
        log = f"""
            DEBUG {fake_date}: User '{self.fake.user_name()}' logged in from {self.fake.ipv4()}.
            WARNING {fake_date + timedelta(minutes=random.randint(5, 30))}: Failed to write to /dev/sda1 (I/O error).
            """
        # Inject random corruption
        corruption = f"\x00\xFF\xFE" + self.fake.binary(64)  # Binary garbage
        position = random.randint(0, len(log))  # Random break point
        return log[:position] + corruption + log[position:]


    def generate_fake_sql_dump(self) -> str:
        dump = """-- MySQL dump 10.16

        INSERT INTO users VALUES (1, 'admin', '{}');
        INSERT INTO users VALUES (2, 'guest', '{}');
        """.format(
            ''.join(random.choices("0123456789abcdef", k=32)),
            ''.join(random.choices("0123456789abcdef", k=32))
        )
        return dump + "\n\x00\x00ERROR: Disk full (code 28)\n"



    def create_directory(self, dir_path: str) -> None:
        """Creates a directory at the specified path."""
        try:
            os.makedirs(dir_path, exist_ok=True)
            logging.info(f"{dir_path} is created by agent.")
            return
        except OSError as error:
            logging.error("Attemted to create a directory by agent but FAILED.")
            raise

    def create_file(self, path:str, filename:str, content_type: Optional[str]=None, backdate_days:Optional[int]=None) -> None:
        """Creates a file with optional backdating options.
        Be carefull when u backdate, because some random files like 'solo.txt'
        can not be older than some fundamental system directory files likes .ssh or .bashrc .
        """
        try:

            if content_type:
                content = {
                    'log': self.generate_corrupted_log(),
                    'pgp': self.generate_fake_pgp_message(),
                    'sql': self.generate_fake_sql_dump(),
                    'text': self.generate_file_content(),
                    'failed_backup': self.generate_failed_backup()
            }.get(content_type, "")

            filepath = os.path.join(path, filename)
            with open(filepath, 'w') as file:
                file.write(content)
            logging.info(f"File named {filename} is created at {path} by agent with the content_type of {content_type}")

            if backdate_days is not None:
                self.backdate_file(filepath, backdate_days)
                logging.info(f"Backdated {filename} by {backdate_days} days.")
            return
        except OSError as e:
            logging.error(f"Attempted to create create a file by agent but FAILED.")
            raise

    def backdate_file(self, 
        path:str,
        days: Optional[int] = None,
        min_days: int = 30,
        max_days: int = 800) -> None:#dont know if it is none
        """Backdates a file to be more believable,
        if all the files generated at the exact same day it would not be realistic."""
        try:
            backdate_days = days if days is not None else random.randint(min_days, max_days)
            timestamp = time.time() - (backdate_days *86400)
            os.utime(path, (timestamp, timestamp))
            logging.info(f"Backdated {path} by {backdate_days}.")
            return
        except Exception as ex:
            logging.error(f"Backdating failed: {str(ex)}")
            raise

    def create_process(self, command:str) -> Optional[int]:
        """Creates a new process with the command.
        Because a realistic system contains starting,working and quiting processes."""
        try:
            process = subprocess.Popen(command, shell=True)
            logging.info(f"Process started with PID: {process.pid}")
            return process.pid
        except Exception as ex:
            logging.error(f"Failed to start process: {ex}")
            raise



    def create_user(self, username:Optional[str]=None, home_dir:Optional[str]=None, shell:str="/bin/bash", system_account:Optional[bool]=False) ->None:
        """Creates a user account with optional parameters of password, home directory."""
        try:
            password = self.generate_password()
            if username is None:
                username = self.generate_username()

            cmd = ["useradd"]

            if system_account:
                cmd.append("--system")
            else:
                if home_dir:
                    cmd.extend(["--home-dir", home_dir])
                else:
                    cmd.extend(["--create-home"])
                cmd.extend(["--shell", shell])
            cmd.append(username)

            subprocess.run(cmd, check=True)
            if password and not system_account:
                subprocess.run(
                    ["chpasswd"],
                    input=f"{username}:{password}".encode(),
                    check=True
                )
            logging.info(f"Created a user: {username} , password: {password}.")
        except Exception as ex:
            logging.error(f"Failed to create user: {ex}")
            raise


    def create_group(self, group_name:Optional[str]=None, gid:Optional[int]=None, system_group:Optional[bool]=False) ->None:
        """Creates a group with optional GID."""
        try:
            if group_name is None:
                group_name = self.generate_username()

            cmd = ["groupadd"]

            if system_group:
                cmd.append("--system")
            if gid is not None:
                cmd.extend(["--gid", str(gid)])

            cmd.append(group_name)

            subprocess.run(cmd, check=True)
            logging.info(f"Created a group named {group_name}")
        except Exception as ex:
            logging.error(f"Failed to create group: {ex}")
            raise



    def change_file_owner(self, path:str, user:Optional[Union[str, int]]=None, group:Optional[Union[str, int]]=None) -> bool:
        """Changes ownership of a file/directory.
        But for making it more realistic, do not forget some files are most likely to be under root than user such as '..' ."""
        try:
            #converts to numbers
            uid = pwd.getpwnam(user).pw_uid if isinstance(user, str) else user
            gid = grp.getgrnam(group).gr_gid if isinstance(group, str) else group

            stat_info = os.stat(path)
            #if both parameters are not given at the same time, this saves the existing ones.
            if uid is None:
                uid = stat_info.st_uid
            if gid is None:
                gid = stat_info.st_gid

            os.chown(path, uid, gid)
            logging.info(f"Changed the file owner of {path}")
            return True
        except Exception as ex:
            logging.error(f"Failed to change file owner: {ex}")
            raise


    def generate_tool_calls(self, prompt: str) -> Optional[Dict]:
        
        tools_description = self.get_all_tool_descriptions()
        
        structured_prompt = f"""You are a honeypot automation agent. You can perform the following tools:

        {tools_description}

        Your task is: {task}

        Respond ONLY with a JSON object in the format:
        {{
        "tool_name": "create_file",
        "args": {{
            "path": "/tmp",
            "filename": "test.log",
            "content_type": "log"
        }}
        }}

        Do NOT include explanations, do NOT deviate from the format.
        """

        mistral_prompt = f"<s>[INST] {structured_prompt.strip()} [/INST]"


        try:
            input_ids = self.tokenizer(mistral_prompt, return_tensors="pt").input_ids.to("cpu")
            output_ids = self.model.generate(
                input_ids,
                max_new_tokens=256,
                do_sample=True,
                temperature=0.3,
                top_p=0.9
            )
            decoded_output = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)

            logging.info(f"Model output: {decoded_output}")
            parsed = json.loads(decoded_output)
            return parsed
        except Exception as e:
            logging.error(f"Failed to parse model output: {e}")
            return None


    def log_action(self, action: FileSystemAgentActions) -> None:
        """Logs an action to memory while redacting sensitive info."""
        sanitized_args = {
            k: "******" if "password" in k.lower() else v
            for k, v in action.arguments.items()
        }
        self.actions_log.append(
            FileSystemAgentActions(
                function_name=action.function_name,
                arguments=sanitized_args,
                result=action.result,
                success=action.success,
                timestamp=action.timestamp
            )
        )


    def get_action_history(self) -> str:
        """Returns a formatted string of the last 5 actions for context."""
        return "\n".join([
            f"{action.function_name}({action.arguments}) → {action.result[:50]}..."
            for action in self.actions_log[-5:]
        ])


    def execute_function(self, func_name: str, args: Dict[str, Any]) -> FileSystemAgentActions:
        """Executes a function with safety checks."""
        try:
            
            # 2. Find matching tool
            tool = next((t for t in self.tools if t.name == func_name), None)
            if not tool:
                raise ValueError(f"Unknown tool: {func_name}")
            
            # 3. Execute and log
            result = tool.execute(**args)
            action = FileSystemAgentActions(
                function_name=func_name,
                arguments=args,
                result=str(result),
                success=True
            )
            self.result_producer.send(
                topic='task-results',
                value=json.dumps({
                    "agent": "filesystem_agent",
                    "task_id": self.current_task,
                    "action": func_name,
                    "status": "completed",
                    "result": str(result),
                    "timestamp": int(time.time()*1000)
                }).encode('utf-8')
            )
            self.actions_log.append(action)
            return action
            
        except Exception as e:
            action = FileSystemAgentActions(
                function_name=func_name,
                arguments=args,
                result=str(e),
                success=False
            )

            self.result_producer.send(
                topic='task-results',
                value=json.dumps({
                    "agent": "filesystem_agent",
                    "task_id": self.current_task,
                    "action": func_name,
                    "status": "failed",
                    "error": str(e),
                    "timestamp": int(time.time()*1000)
                }).encode('utf-8')
            )
            self.actions_log.append(action)
            return action
    

    def run(self, task: str) -> None:
        """Main execution loop."""
        self.current_task = task
        logging.info(f"Starting task: {task}")

        try:
            tool_response = self.generate_tool_calls(task)
            tool_name = tool_response["tool_name"]
            args = tool_response["args"]
            
            if not tool_response:
                raise ValueError("No valid tools generated")

            if tool_name not in self.tool_dispatch:
                logging.error(f"Invalid tool: {tool_name}")
                return

            if tool_name and args:
                action = self.execute_function(tool_name, args)
                self.log_action(action)
            logging.info(f"Executed {tool_name} (Success: {action.success})")

        except Exception as e:
            logging.error(f"Task failed: {str(e)}")
        finally:
            self.current_task = None


    def start_consuming(self):
        logging.info("Starting the Kafka consumer loop.")

        try:
            for msg in self.command_consumer:
                try:
                    task = json.load(msg.value.decode('utf-8'))
                    logging.info(f"Received task: {task}")

                    self.current_task = task,get('task_id', str(uuid.uuid4()))
                    task_command = task['command']
                    task_args = task.get('args', {})

                    if task_command in self.tool_dispatch:
                        action = self.execute_function(task_command, task_args)
                        logging.info(f"Processed {task_command} (Success: {action.success})")
                    else:
                        logging.error(f"Unknown commanc: {task_command}")

                except json.JSONDecodeError as er:
                    logging.error(f"Invalid message format: {er}")
                except Exception as ex:
                    logging.error(f"Error processing message: {ex}")
        except KeyboardInterrupt:
            logging.info("Shutting down consumer!")
        finally:
            self.cleanup()


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[
            logging.FileHandler('app.log'),
            logging.StreamHandler()  # Print logs to console
        ],
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    agent = AutonomousFileAgent()
    try:
        # Start consuming messages
        agent.start_consuming()
    except Exception as e:
        logging.error(f"Agent crashed: {e}")
    finally:
        agent.cleanup()