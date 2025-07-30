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
import time
import json
from duckduckgo_search import ddg 
import random
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import InferenceClient
import shlex  # For safe command splitting

# Initialize Faker
fake = Faker()

# --- Helper Functions ---
def generate_username() -> str:
    return fake.user_name()

def generate_password(length:int=10, require_special_chars:bool=True, 
                    require_upper_case:bool=True, require_lower_case:bool=True,
                    require_digits:bool=True) -> str:
    return fake.password(
        length=length,
        special_chars=require_special_chars,
        digits=require_digits,
        upper_case=require_upper_case,
        lower_case=require_lower_case,
    )

def generate_file_content() -> str:
    return fake.text()

def generate_fake_pgp_message() -> str:
    fake_binary_data = fake.binary(length=256)
    fake_base64 = base64.b64encode(fake_binary_data).decode('utf-8')
    formatted_base64 = '\n'.join([fake_base64[i:i+64] for i in range(0, len(fake_base64), 64)])
    return f"""-----BEGIN PGP MESSAGE-----
        Version: OpenPGP 2.0
        Comment: Created by GPG 2.4.3 (Linux)

        {formatted_base64}
        -----END PGP MESSAGE-----"""

def generate_failed_backup() -> str:
    return f"""
        === Database Backup {fake.date_between(start_date="-3y", end_date="today")} ===
        TABLE users: 12 records dumped.
        \x00\x00ERROR: Connection lost at record 13/50.
        RAW DUMP: {fake.uuid4()}
        {fake.text()}"""

def generate_corrupted_log() -> str:
    fake_date = fake.date_time_between(start_date="-3y", end_date="now")
    log = f"""
        DEBUG {fake_date}: User '{fake.user_name()}' logged in from {fake.ipv4()}.
        WARNING {fake_date + timedelta(minutes=random.randint(5, 30))}: Failed to write to /dev/sda1 (I/O error)."""
    corruption = f"\x00\xFF\xFE" + fake.binary(64)
    position = random.randint(0, len(log))
    return log[:position] + corruption + log[position:]

def generate_fake_sql_dump() -> str:
    dump = """-- MySQL dump 10.16
    INSERT INTO users VALUES (1, 'admin', '{}');
    INSERT INTO users VALUES (2, 'guest', '{}');
    """.format(
        ''.join(random.choices("0123456789abcdef", k=32)),
        ''.join(random.choices("0123456789abcdef", k=32))
        )
    return dump + "\n\x00\x00ERROR: Disk full (code 28)\n"

# --- Filesystem Operations ---
def create_directory(dir_path: str) -> None:
    try:
        os.makedirs(dir_path, exist_ok=True)
        logging.info(f"Directory created: {dir_path}")
    except OSError as error:
        logging.error(f"Directory creation failed: {error}")

def create_file(path:str, filename:str, content_type: Optional[str]=None, backdate_days:Optional[int]=None) -> None:
    try:
        content = {
            'log': generate_corrupted_log(),
            'pgp': generate_fake_pgp_message(),
            'sql': generate_fake_sql_dump(),
            'text': generate_file_content(),
            'failed_backup': generate_failed_backup()
        }.get(content_type, "")
        
        filepath = os.path.join(path, filename)
        with open(filepath, 'w') as file:
            file.write(content)
        
        if backdate_days:
            backdate_file(filepath, backdate_days)
            
    except Exception as e:
        logging.error(f"File creation failed: {e}")

def backdate_file(path:str, days: Optional[int]=None, min_days:int=30, max_days:int=800) -> None:
    try:
        backdate_days = days if days else random.randint(min_days, max_days)
        timestamp = time.time() - (backdate_days * 86400)
        os.utime(path, (timestamp, timestamp))
    except Exception as e:
        logging.error(f"Backdating failed: {e}")

def create_process(command:str) -> Optional[int]:
    try:
        # Safe execution with shell=False
        process = subprocess.Popen(
            shlex.split(command),
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return process.pid
    except Exception as e:
        logging.error(f"Process creation failed: {e}")
        return None

def create_user(username:Optional[str]=None, home_dir:Optional[str]=None, 
               shell:str="/bin/bash", system_account:bool=False) -> None:
    try:
        password = generate_password()
        username = username or generate_username()
        
        cmd = ["useradd"]
        if system_account:
            cmd.append("--system")
        else:
            cmd.extend(["--create-home", "--shell", shell])
            if home_dir:
                cmd.extend(["--home-dir", home_dir])
        
        cmd.append(username)
        subprocess.run(cmd, check=True)
        
        if not system_account:
            subprocess.run(
                ["chpasswd"],
                input=f"{username}:{password}".encode(),
                check=True
            )
    except Exception as e:
        logging.error(f"User creation failed: {e}")

def create_group(group_name:Optional[str]=None, gid:Optional[int]=None, 
                system_group:bool=False) -> None:
    try:
        group_name = group_name or generate_username()
        cmd = ["groupadd"]
        
        if system_group:
            cmd.append("--system")
        if gid:
            cmd.extend(["--gid", str(gid)])
            
        cmd.append(group_name)
        subprocess.run(cmd, check=True)
    except Exception as e:
        logging.error(f"Group creation failed: {e}")

def change_file_owner(path:str, user:Optional[Union[str,int]]=None, 
                     group:Optional[Union[str,int]]=None) -> bool:
    try:
        uid = pwd.getpwnam(user).pw_uid if isinstance(user, str) else user
        gid = grp.getgrnam(group).gr_gid if isinstance(group, str) else group
        
        stat = os.stat(path)
        uid = uid or stat.st_uid
        gid = gid or stat.st_gid
        
        os.chown(path, uid, gid)
        return True
    except Exception as e:
        logging.error(f"Ownership change failed: {e}")
        return False

# --- Tool Definitions ---
tools = [
    {
        "type": "function",
        "function": {
            "name": "ddg",
            "description": "Search DuckDuckGo for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string"},
                    "max_results": {"type": "integer", "default": 3}
                },
                "required": ["keywords"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Creates a directory at the specified path.Before you create a file you need to create the path that you want to . Be carefull with the path names , you can search the internet for what paths there are in the real linux systems.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "Path of the directory to create."},
                },
                "required": ["dir_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Creates a file with optional content type and backdating options. Before you create a file you need to create the path you want to put the file at. Be carefull with the file names they need to be compatible with the file path. If the path is not something important that does not come from system itself then filename can be random but if the path is something that is more than ./Downloads then you should pick a filename that is likely to be under that directory path. ",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory where the file will be created."},
                    "filename": {"type": "string", "description": "Name of the file."},
                    "content_type": {
                        "type": "string", 
                        "description": "Type of content to generate (log, pgp, sql, text, failed_backup)",
                        "enum": ["log", "pgp", "sql", "text", "failed_backup"]
                    },
                    "backdate_days": {"type": "integer", "description": "Number of days to backdate the file."},
                },
                "required": ["path", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "backdate_file",
            "description": "Backdates a file to appear older than it is. System files is more likely to be older , so keep in mind which file path and filename you are backdating.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to backdate."},
                    "days": {"type": "integer", "description": "Exact number of days to backdate (optional)."},
                    "min_days": {"type": "integer", "description": "Minimum days for random backdating (default 30)."},
                    "max_days": {"type": "integer", "description": "Maximum days for random backdating (default 800)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_process",
            "description": "Creates a new process with the given command. Make the system realistic , do not exaggerate. ",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_user",
            "description": "Creates a user account with optional parameters. Simulate a real system , how many user most likely to be in a linux file system?",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Name of the user to create (optional, will generate if not provided)."},
                    "home_dir": {"type": "string", "description": "Home directory path (optional)."},
                    "shell": {"type": "string", "description": "Login shell (default: /bin/bash)."},
                    "system_account": {"type": "boolean", "description": "If True, creates a system account."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_group",
            "description": "Creates a group with optional GID.Also you can search for internet for this one for how many groups are usually are there and what are the common names for them?",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_name": {"type": "string", "description": "Name of the group to create (optional, will generate if not provided)."},
                    "gid": {"type": "integer", "description": "Group ID (optional)."},
                    "system_group": {"type": "boolean", "description": "If True, creates a system group."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "change_file_owner",
            "description": "Changes ownership of a file/directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file/directory."},
                    "user": {"type": ["string", "integer"], "description": "User name or ID (optional)."},
                    "group": {"type": ["string", "integer"], "description": "Group name or ID (optional)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_password",
            "description": "Generates a random password with customizable complexity. **DO NOT CALL DIRECTLY**—this function is used internally by the system. Only provide parameter suggestions when explicitly asked. ",
            "parameters": {
                "type": "object",
                "properties": {
                    "length": {"type": "integer", "description": "Length of the password (default 10)."},
                    "require_special_chars": {"type": "boolean", "description": "Include special characters (default True)."},
                    "require_upper_case": {"type": "boolean", "description": "Include uppercase letters (default True)."},
                    "require_lower_case": {"type": "boolean", "description": "Include lowercase letters (default True)."},
                    "require_digits": {"type": "boolean", "description": "Include digits (default True)."},
                },
            }
        },
    },
]

# --- Agent Core ---
class FileSystemAgentActions(BaseModel):
    function_name: str = Field(...)
    arguments: Dict[str, Any] = Field(...)
    result: str = Field(...)
    success: bool = Field(...)
    timestamp: float = Field(default_factory=time.time)

class AutonomousAgent:
    def __init__(self):
        self.llm = InferenceClient(model="mistralai/Mistral-7B-Instruct-v0.1")
        self.tools = tools
        self.actions_log = []
    
    def log_action(self, action: FileSystemAgentActions) -> None:
        sanitized_args = {
            k: "REDACTED" if "password" in k.lower() else v 
            for k,v in action.arguments.items()
        }
        self.actions_log.append(
            FileSystemAgentActions(
                function_name=action.function_name,
                arguments=sanitized_args,
                result=action.result,
                success=action.success
            )
        )
    
    def get_action_history(self) -> str:
        return "\n".join(
            f"{a.function_name}({a.arguments}) → {a.result[:50]}..."
            for a in self.actions_log[-3:]
        )
    
    def execute_function(self, func_name: str, args: Dict) -> FileSystemAgentActions:
        try:
            result = globals()[func_name](**args)
            return FileSystemAgentActions(
                function_name=func_name,
                arguments=args,
                result=str(result),
                success=True
            )
        except Exception as e:
            return FileSystemAgentActions(
                function_name=func_name,
                arguments=args,
                result=str(e),
                success=False
            )
    
    def generate_tool_calls(self, prompt: str) -> Optional[Dict]:
        try:
            response = self.llm.text_generation(
                prompt,
                max_new_tokens=512,
                stop_sequences=["```"]
            )
            json_str = response.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        except Exception as e:
            logging.error(f"Tool generation failed: {e}")
            return None
    
    def run(self, task: str) -> None:
        prompt = f"""
        You are a Linux filesystem honeypot agent. Create realistic system artifacts.
        Available tools: {[t['function']['name'] for t in self.tools]}
        History:
        {self.get_action_history()}
        
        Task: {task}
        
        Respond ONLY with JSON like:
        ```json
        {{
            "tool_calls": [{{
                "function": {{
                    "name": "tool_name",
                    "arguments": {{...}}
                }}
            }}]
        }}
        ```
        """
        
        try:
            tool_response = self.generate_tool_calls(prompt)
            if not tool_response:
                raise ValueError("No valid tools generated")
            
            for call in tool_response.get("tool_calls", []):
                func_name = call["function"]["name"]
                args = call["function"]["arguments"]
                
                if func_name not in globals():
                    logging.error(f"Invalid tool: {func_name}")
                    continue
                
                action = self.execute_function(func_name, args)
                self.log_action(action)
                
        except Exception as e:
            logging.error(f"Agent failed: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        filename='honeypot.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    agent = AutonomousAgent()
    agent.run("Create a realistic Linux filesystem for a honeypot. Create files, users, groups, and processes that would appear authentic to an attacker.")