# Copyright (c) 2009 Upi Tamminen <desaster@gmail.com>
# Updated for T-Pot with AI integration points

import getopt
import os
import random
from faker import Faker
import time
import json
from typing import Any
from urllib import parse
import hashlib
from twisted.internet import error
from twisted.internet.defer import inlineCallbacks
from twisted.python import log
from twisted.web.iweb import UNKNOWN_LENGTH
import treq
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.web.http_headers import Headers
from urllib.parse import urlparse
from agents.ai_interactor import AiInteractorWget
from agents.master_agent import MasterAgent
from agents.MPT_file_system_creation_agent import AutonomousFileAgent
import metrics

# AI Configuration (will be set via T-Pot config)
AI_ENABLED = False
AI_CONTAINER_URL = "http://ai-agent:5000"  # Default Docker network address

try:
    from cowrie.fake_commands import ai_interactor
except ImportError:
    ai_interactor = None
    log.msg("AI Interactor module (ai_interactor.py) not found or not in PYTHONPATH!")
from cowrie.core.artifact import Artifact
from cowrie.core.config import CowrieConfig
from cowrie.shell.command import HoneyPotCommand

commands = {}

#for the display of time
def tdiff(seconds: int) -> str:
    t = seconds
    days = int(t / (24 * 60 * 60))
    t -= days * 24 * 60 * 60
    hours = int(t / (60 * 60))
    t -= hours * 60 * 60
    minutes = int(t / 60)
    t -= minutes * 60

    s = f"{t}s"
    if minutes >= 1:
        s = f"{minutes}m {s}"
    if hours >= 1:
        s = f"{hours}h {s}"
    if days >= 1:
        s = f"{days}d {s}"
    return s

#for the display of bytes
def sizeof_fmt(num: float) -> str:
    for x in ["bytes", "K", "M", "G", "T"]:
        if num < 1024.0:
            return f"{num}{x}"
        num /= 1024.0
    raise ValueError

# Luciano Ramalho @ http://code.activestate.com/recipes/498181/
def splitthousands(s: str, sep: str = ",") -> str:
    if len(s) <= 3:
        return s
    return splitthousands(s[:-3], sep) + sep + s[-3:]


class CommandWget(HoneyPotCommand):
    """
    wget command modified for T-Pot with AI hooks
    """

    file_types = {
        'exe': ('application/octet-stream', 2500000),
        'dll': ('application/octet-stream', 1500000),
        'msi': ('application/octet-stream', 3000000),
        'js': ('text/javascript', 45000),
        'vbs': ('text/vbscript', 38000),
        'ps1': ('application/x-powershell', 55000),
        'bat': ('application/x-msdownload', 12000),
        'sh': ('application/x-sh', 15000),
        'jar': ('application/java-archive', 1800000),
        'zip': ('application/zip', 4200000),
        'rar': ('application/vnd.rar', 3800000),
        '7z': ('application/x-7z-compressed', 5000000),
        'tar': ('application/x-tar', 2800000),
        'gz': ('application/gzip', 1900000),
        'doc': ('application/msword', 850000),
        'docx': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 1200000),
        'docm': ('application/vnd.ms-word.document.macroEnabled.12', 1500000),
        'xls': ('application/vnd.ms-excel', 950000),
        'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 1400000),
        'xlsm': ('application/vnd.ms-excel.sheet.macroEnabled.12', 1800000),
        'ppt': ('application/vnd.ms-powerpoint', 2200000),
        'pptm': ('application/vnd.ms-powerpoint.presentation.macroEnabled.12', 2500000),
        'pdf': ('application/pdf', 2100000),
        'jpg': ('image/jpeg', 1250000),
        'png': ('image/png', 1800000),
        'gif': ('image/gif', 850000),
        'svg': ('image/svg+xml', 28000),
        'html': ('text/html', 65000),
        'htm': ('text/html', 62000),
        'php': ('application/x-httpd-php', 48000),
        'asp': ('application/asp', 52000),
        'conf': ('text/plain', 12000),
        'cfg': ('text/plain', 9500),
        'ini': ('text/plain', 7800),
        'env': ('text/plain', 4500),
        'sql': ('application/sql', 68000),
        'db': ('application/x-sqlite3', 3200000),
        'csv': ('text/csv', 125000),
        'abw': ('application/x-abiword', 320000),
        'apng': ('image/apng', 950000),
        'arc': ('application/x-freearc', 1800000),
        'avif': ('image/avif', 1100000),
        'avi': ('video/x-msvideo', 5800000),
        'bin': ('application/octet-stream', 1600000),
        'bmp': ('image/bmp', 2400000),
        'bz': ('application/x-bzip', 2200000),
        'txt': ('text/plain', 12000),
        'dat': ('application/octet-stream', 18000)
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not self.args:
            ext = 'txt'
        else:
            self.ext = self.args[0].split('.')[-1].lower() if '.' in self.args[0] else 'txt'
        self.mime_type, self.content_length = self.file_types.get(self.ext, ('application/octet-stream', 0))
        
        self.kafka_producer = KafkaProducer({
            'client.id': f'wget-{self.protocol.getSessionId()}'
        })

        self.ai_context = {
            'honeypot': 'cowrie',
            'command': 'wget',
            'outfile': None,
            'quiet': False,
            'start_time': time.time(),
            'url': None,
            'host': None,
            'ip': self.protocol.getClientIP(),
            'user': self.protocol.user.username if self.protocol.user else 'unknown',
            'metrics': metrics.Metrics(),
            'ai_interactor': AiInteractorWget(mime_type=self.mime_type) if AI_ENABLED else None
        }
        
        # Original implementation variables
        self.outfile: str | None = None
        self.artifact = Artifact("wget-download")
        self.currentlength: int = 0
        self.totallength: int = 0
        self.proglen: int = 0
        self.url: bytes = b''
        self.host: str = ''
        self.started: float = 0.0
        self.speed: float = 0.0
        self.contenttype: str = 'text'
        self.lastupdate: float = 0.0

    def _log(self, event_type: str, url: str, status: str = None):
        parsed = urlparse(url)
        duration = time.time() - self.start_time
        self.ai_context['duration'] = duration

        log_data = {
            'event': f"wget_{event_type}",
            'host': self.host,
            'url': self.url.decode() if isinstance(self.url, bytes) else self.url,
            'status': status,
            'ai_enabled': AI_ENABLED,
            'ip': self.ai_context['ip'],
            'user': self.ai_context['user'],
            'duration': tdiff(time.time() - self.ai_context['start_time']),
            'timestamp': time.time(),
        }
        log.msg(json.dumps(log_data))
        return log_data

    def _get_ai_response(self, stage: str, options: list = None, **kwargs) -> str:
        options = options or []

        if not AI_ENABLED or not self.ai_interactor:
            return {'success': False, 'response': None}

        context = {
            'command': 'wget',
            'stage': stage,
            'url': self.url.decode() if isinstance(self.url, bytes) else self.url,
            'host': self.host,
            'outfile': self.outfile,
            'quiet': self.quiet,
            **self.ai_context,
            **kwargs
        }
        
        try:
            self.ai_context['metrics'].start_timer()
            response = self.ai_context['ai_interactor'].get_response(context)
            self.ai_context['metrics'].log_kafka_latency()
            
            if response and response.get('status') == 'success':
                self.ai_context['metrics'].log_categorization(True)
                return {'success': True, 'response': response.get('result', '')}
            
            return {'success': False, 'response': None}
            
        except Exception as e:
            log.msg(f"AI processing failed: {e}")
            return {'success': False, 'response': None}


    def file_metadata(self, url:str, outfile: str, quiet: bool=False) -> dict:
        download_id = str(uuid.uuid4())
        
        # Send start event
        self.kafka_producer.send_event(
            topic="download_events",
            event_type="download_start",
            payload={
                "download_id": download_id,
                "url": url,
                "filename": outfile,
                "source_ip": self.ai_context['ip'],
                "user": self.ai_context['user'],
                "session_id": self.protocol.getSessionId()
            }
        )
        
        # Send completion event
        self.kafka_producer.send_event(
            topic="download_events",
            event_type="download_complete",
            payload={
                "download_id": download_id,
                "size": content_length,
                "duration_ms": int((time.time() - start_time) * 1000),
                "status": "success"
            }
        )
        return {
            'url': url,
            'filename': outfile,
            'size': self.content_length,
            'content_type': self.content_type,
            'file_type': self.ext,
            'success': True
            }


    @inlineCallbacks
    def start(self): # main execution start point

        url: str

        # Parse command line
        try:
            optlist, args = getopt.getopt(self.args, "cqO:P:", ["header="])
        except getopt.GetoptError as err:
            self.errorWrite(f"wget: {err}\n")
            self.exit()
            return

        # Get URL
        url = args[0].strip() if args else None
        if not url:
            self.errorWrite("wget: missing URL\n")
            self.errorWrite("Usage: wget [OPTION]... [URL]...\n\n")
            self.errorWrite("Try `wget --help' for more options.\n")
            self.exit()
            return

        # Validate url
        if "://" not in url:
            url = f"https://{url}"
        try:
            urldata = urlparse(url)
            self.host = urldata.hostname
            self.ai_context.update({
                'url': url,
                'host': self.host,
                'outfile': self.outfile,
                'quiet': self.quiet
            })
        except Exception as ex:
            self.errorWrite(f"wget: Invalid URL - {str(ex)}\n")
            self._log('error', 'invalid_url')
            self.exit()
            return

        faker = Faker()
        faker.seed_instance(self.host) #to make the ip's belong to the same host
        # Check if host is allowed
        self.Write(f"Host: {self.host}\n")
        fake_ips = [faker.ipv4() for _ in range(4)]
        resolved_ip_str = ", ".join(fake_ips)
        self.errorWrite(f"Resolving {self.host} ({self.host})... {resolved_ip_str}\n")
        first_ip = fake_ips[0]
        port_to_display = urldata.port if urldata.port else (443 if urldata.scheme == 'https' else 80)
        self.errorWrite(f"Connecting to {self.host} ({self.host})|{first_ip}|:{port_to_display}... connected.\n")

        allowed = yield communcation_allowed(self.host)
        if not allowed:
            log.msg(f"Blocked host access attempt: {self.host}")
            self.errorWrite(f"wget: unable to resolve host address '{self.host}'\n")
            self._log('blocked', 'host_blocked')
            self.exit()
            return None

        self.url = url.encode("utf8")

        #parse options
        for opt, arg in optlist:
            if opt == '-o':
                if not arg:  # check for missing argument
                    self.errorWrite("Output file (-o) requires a filename")
                self.ai_context['outfile'] = arg
                self.outfile = self.ai_context['outfile']
            elif opt == '-q':
                self.ai_context['quiet'] = True
            else:
                self.errorWrite(f"Unknown option: {opt}")

        # determine output file
        if self.outfile is None:
            self.ai_context['outfile'] = urldata.path.split("/")[-1] or "index.html"
        if self.ai_context['outfile'] != "-":
            resolved_outfile_path = self.fs.resolve_path(self.ai_context['outfile'], self.protocol.cwd)
            path = os.path.dirname(resolved_outfile_path) 
            if not path or not self.fs.exists(path) or not self.fs.isdir(path):
                self.errorWrite(
                    f"wget: {self.ai_context['outfile']}: Cannot open: No such file or directory\n"
                )
                self._log('error', 'invalid_path')
                self.exit()
                return
            self.outfile_path_for_artifact = resolved_outfile_path 
        else:
            self.outfile_path_for_artifact = "-" 


        # Initial connection message (AI or fallback)
        if not self.ai_context['quiet']:
            ai_response = self._get_ai_response('connect')
            if ai_response['success']:
                self.errorWrite(ai_response['response'] + "\n")
            else:
                tm = time.strftime("%Y-%m-%d %H:%M:%S")
                self.errorWrite(f"--{tm}--  {url}\n")
                port_to_display = urldata.port if urldata.port else (443 if urldata.scheme == 'https' else 80)
                self.errorWrite(f"Connecting to {self.host} ({self.host})|{first_ip}|:{port_to_display}... connected.\n")

        self.deferred = self.wget_download(self.url, headers=[])
        if self.deferred:
            self.deferred.addCallback(self._handle_simulated_response)
            self.deferred.addErrback(self._handle_simulated_error)
        else:
            self._handle_early_error()
    
    def _handle_early_error(self):
        if AI_ENABLED and not self.quiet:
            ai_response = self._get_ai_response(
                'error',
                status='early_error',
                error_type='no_deferred'
            )
            if ai_response['success']:
                self.errorWrite(f"[AI] {ai_response['response']}\n")
        self._log('error', 'early_error')
        self.exit() 

    def _handle_simulated_error(self):
        errors = [
            ("Connection timed out", "timeout"),
            ("404 Not Found", "http_error"),
            ("SSL certificate problem", "ssl_error")
        ]
        msg, error_type = random.choice(errors)
        self.errorWrite(f"wget: {msg}\n")
        self._log('download_failed', error_type)
        self.exit()

    def _handle_simulated_response(self, response):
        self.started = time.time()
        self.totallength = response.length

        if not self.ai_context['quiet']:
            self.errorWrite("HTTP request sent, awaiting response...")
            time.sleep(0.5)
            self.errorWrite(" 200 OK\n")
            self.errorWrite(f"HTTP/1.1 200 OK\n")
            self.errorWrite(f"Length: {self.totallength} ({sizeof_fmt(self.totallength)}) "
                          f"[{response.headers.getRawHeaders(b'content-type')[0].decode()}]\n")
            self.errorWrite(f"Saving to: '{self.outfile}'\n\n")

        response.deliveryBody(self.protocol)

    def wget_download(self, url:str, headers:list = None) -> Any:
        self._log('simulated_download_start', url=url)
        defer_obj = Deferred()
        #network delay
        delay = 0/5 if self.ai_context['quiet'] else 1.5
        #schedule response
        reactor.callLater(delay, lambda:defer_obj.callback(
            self._create_simulated_response(url)
        ))
        return defer_obj

    def _create_simulated_response(self,url:str) -> object:

        ext = url.split('.')[-1].lower() if '.' in url else 'txt'
        content_type, content_length = self.file_types.get(ext, self.file_types['txt'])

        class FakeResponse:
            headers = Headers({
                b'content-type': [content_type.encode()],
                b'content-length': [str(content_length).encode()]
            })
            remaining = content_length
            http_status = 200
            start_time = time.time()
            
            def deliverBody(self, protocol):
                # Simulate chunked data delivery
                chunk_size = 4096
                remaining = content_length
                
                def send_chunk():
                    nonlocal remaining
                    if remaining <= 0:
                        protocol.connectionLost(None)
                        return
                    
                    this_chunk = min(chunk_size, remaining)
                    protocol.dataReceived(b'X' * this_chunk)  # Fake data
                    remaining -= this_chunk
                    
                    # Schedule next chunk with realistic timing
                    reactor.callLater(
                        random.uniform(0.02, 0.15),
                        send_chunk
                    )
                
                send_chunk()
        
        return FakeResponse()

    def collect(self, data:bytes) -> None:
        self.currentlength += len(data)
        if not self.ai_context['quiet']:
            elapsed = time.time() - self.started
            speed = self.currentlength /elapsed if elapsed > 0 else 0
            percent = min(100, self.currentlength / self.totallength *100)

            progress = ("\r{percent:3}% [{bar:<40}] {size} {speed:3.1f}K/s"
                       .format(
                           percent=int(percent),
                           bar='=' * int(percent * 0.4) + '>',
                           size=splitthousands(str(self.currentlength)).ljust(12),
                           speed=speed / 1024))
            self.errorWrite(progress.ljust(self.proglen))
            self.proglen = len(progress)


    def collection_complete(self):
        elapsed = time.time() - self.started
        base_speed = self.totallength / elapsed
        speed = base_speed * random.uniform(0.85, 1.15)

        
        if not self.ai_context['quiet']:
            self.errorWrite("\r100% [{}] {} {:3.1f}K/s\n\n".format(
                '=' * 39 + '>',
                splitthousands(str(self.totallength)).ljust(12),
                speed / 1024))
            
            self.errorWrite("{} ({:3.1f} KB/s) - '{}' saved [{}/{}]\n\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"),
                speed / 1024,
                self.outfile,
                self.totallength,
                self.totallength))
        
        # here call the agent to create a file acording to it 
        try:
            master_agent = MasterAgent()
            result = master_agent.handle_file_download(
                url=self.url.decode() 
                if isinstance(self.url, bytes) 
                else self.url, 
                outfile=self.outfile, 
                ip=self.ai_context['ip'], 
                user=self.ai_context['user'])

            if not results.get('file_creation', {}).get('success'):
                self.errorWrite('Warning: File creation completed with issues\n')
        
        except Exception as ex:
            self.errorWrite(f"Error in file handling {str(ex)}\n")
            self._log('file_creation_error', str(ex))
        

    def handle_CTRL_C(self) -> None:
        self.errorWrite("^C\n")
        self.exit()

# Command registration
commands["/usr/bin/wget"] = Command_wget
commands["wget"] = Command_wget
commands["/usr/bin/dget"] = Command_wget
commands["dget"] = Command_wget