from openai import OpenAI
from pydantic import BaseModel, Field
import os
import logging
import base64
from datetime import timedelta
from typing import Optional, Union, Dict, Any
import Faker
import subprocess
import pwd
import grp
from faker import Faker
import threading
import time
from functools import partial
import json
from duckduckgo_search import ddg 
import random
#logging mantigi degistirilecek

fake = Faker()

def generate_username() -> str:
    return fake.user_name()

def generate_password(length:int=10, 
require_special_chars:Optional[bool]=True, 
require_upper_case:Optional[bool]=True, 
require_lower_case:Optional[bool]=True, 
require_digits:Optional[bool]=True) -> str:
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
    # Generate 256 bytes of random binary data, encode as Base64 (like real PGP)
    fake_binary_data = fake.binary(length=256)
    fake_base64 = base64.b64encode(fake_binary_data).decode('utf-8')
    
    # Split into lines (PGP messages often wrap at 64 chars)
    formatted_base64 = '\n'.join([fake_base64[i:i+64] for i in range(0, len(fake_base64), 64)])
    
    return f"""-----BEGIN PGP MESSAGE-----
        Version: OpenPGP 2.0
        Comment: Created by GPG 2.4.3 (Linux)

        {formatted_base64}
        -----END PGP MESSAGE-----
        """


def generate_failed_backup() -> str:
    return f"""
        === Database Backup {fake.date_between(start_date="-3y", end_date="today")} ===
        TABLE users: 12 records dumped.
        \x00\x00ERROR: Connection lost at record 13/50.
        RAW DUMP: {fake.uuid4()}
        {fake.text()}
        """


def generate_corrupted_log() -> str:
    fake_date = fake.date_time_between(start_date="-3y", end_date="now")
    log = f"""
        DEBUG {fake_date}: User '{fake.user_name()}' logged in from {fake.ipv4()}.
        WARNING {fake_date + timedelta(minutes=random.randint(5, 30))
}: Failed to write to /dev/sda1 (I/O error).
        """
    # Inject random corruption
    corruption = f"\x00\xFF\xFE" + fake.binary(64)  # Binary garbage
    position = random.randint(0, len(log))  # Random break point
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

logging.basicConfig(
    filename='app.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s -%(message)s'
)


def create_directory(dir_path: str) -> None:
    """Creates a directory at the specified path."""
    try:
        os.makedirs(dir_path, exist_ok=True)
        logging.info(f"{dir_path} is created by agent.")
    except OSError as error:
        logging.error("Attemted to create a directory by agent but FAILED.")


def create_file(path:str, filename:str, content_type: Optional[str]=None, backdate_days:Optional[int]=None) -> None:
    """Creates a file with optional backdating options.
     Be carefull when u backdate, because some random files like 'solo.txt' 
     can not be older than some fundamental system directory files likes .ssh or .bashrc .
    """
    try:

        if content_type is not None:
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
        logging.info(f"File named {filename} is created at {path} by agent with the content_type of {content_type}")
        
        if backdate_days is not None:
            backdate_file(filepath, backdate_days)
            logging.info(f"Backdated {filename} by {backdate_days} days.")

    except OSError as e:
        logging.error(f"Attempted to create create a file by agent but FAILED.")


def backdate_file(path:str, 
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
    except Exception as ex:
        logging.error(f"Backdating failed: {str(ex)}")


def create_process(command:str) -> Optional[int]:
    """Creates a new process with the command. 
    Because a realistic system contains starting,working and quiting processes."""
    try:
        process = subprocess.Popen(command, shell=True)
        logging.info(f"Process started with PID: {process.pid}")
        return process.pid
    except Exception as ex:
        logging.error(f"Failed to start process: {ex}")



def create_user(username:Optional[str]=None, home_dir:Optional[str]=None, shell:str="/bin/bash", system_account:Optional[bool]=False) ->None:
    """Creates a user account with optional parameters of password, home directory."""
    try:
        password = generate_password()
        if username is None:
            username = generate_username()

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


def create_group(group_name:Optional[str]=None, gid:Optional[int]=None, system_group:Optional[bool]=False) ->None:
    """Creates a group with optional GID."""
    try:
        if group_name is None:
            group_name = generate_username()

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



def change_file_owner(path:str, user:Optional[Union[str, int]]=None, group:Optional[Union[str, int]]=None) -> bool:
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
        return False


tools = [
    {
        "type": "function",
        "function": {
            "name": "ddg",
            "description": "Search DuckDuckGo for real-time information. Use for researching Linux paths, CVEs, or realistic honeypot data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "Search query."},
                    "max_results": {"type": "integer", "description": "Max results to return (default 3)."},
                },
                "required": ["keywords"],
            },
        },
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


class FileSystemAgentActions(BaseModel):
    """Model for tracking individual agent actions"""
    function_name: str = Field(..., description="Name of the function called")
    arguments: Dict[str, Any] = Field(..., description="Arguments passed to the function")
    result: str = Field(..., description="Result of the operation")
    success: bool = Field(..., description="Whether the operation succeeded")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of action")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

class AutonomousAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.tools = tools
        self.actions_log = []
        self.current_task = None


    def log_action(self, action: FileSystemAgentActions) -> None:
        """Logs an action to memory."""
        self.actions_log.append(action)


    def get_action_history(self) -> str:
        """Returns a formatted string of past actions for context."""
        return "\n".join([
            f"{action.timestamp}: {action.function_name}({action.arguments}) -> {action.result}"
            for action in self.actions_log
        ])


    def execute_function(self, func_name: str, args: Dict[str, Any]) -> FileSystemAgentActions:
        """Execute a function and return structured result"""
        try:
            if func_name == "ddg":
                results = ddg(**args)
                result = json.dumps(results)
            else:   
                func = globals()[func_name]
                result = func(**args)
                action = FileSystemAgentActions(
                    function_name=func_name,
                    arguments=args,
                    result=str(result),
                    success=True
                )
        except Exception as e:
            action = FileSystemAgentActions(
                function_name=func_name,
                arguments=args,
                result=str(e),
                success=False
            )     
        self.log_action(action)
        return action   


    def run(self, task: str) -> None:
        """Execute task autonomously with proper logging"""
        self.current_task = task
        logging.info(f"Starting task: {task}")

        system_message = {
            "role": "system",
            "content": f"You are an autonomous filesystem agent.Your job is to create a mimic of a real linux file system, do not forget you are gonna be the part of a honeypot so make the file system,users,groups,processes etc belivable for the hacker. Past actions:\n{self.get_action_history()}"
        }
        user_message = {"role": "user", "content": task}       

        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[system_message, user_message],
            tools=self.tools
        )

        if tool_calls := response.choices[0].message.tool_calls:
            for call in tool_calls:
                action = self.execute_function(
                    func_name=call.function.name,
                    args=json.loads(call.function.arguments)
                )
                logging.info(f"Action: {action.function_name}, Success: {action.success}")

        logging.info(f"Task completed: {task}")
        self.current_task = None
        
        
if __name__ == "__main__":
    agent = AutonomousAgent()
    agent.run("Create a realistic Linux filesystem for a honeypot. you will see the tools and you be able to create files ,processes users,groups,directories etc. But the important part is to make it realistic for the attacker, you can also search the web for an example of linux file system.")