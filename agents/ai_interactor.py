import json
import random
import time
from typing import Dict, Any, Optional
from transformers import pipeline
from faker import Faker
from twisted.python import log
from master.master_agent import MasterAgent


class AiInteractorWget:

    def __init__(self, mime_type: str = 'text/plain'):
        self.mime_type = mime_type
        self.faker = Faker()
        self.master_agent = MasterAgent()  # For coordination with other agents
        self.llm = pipeline("text-generation", model="distilgpt2", device="cpu")

    
    def _query_ai_service(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        action = payload.get("action")
        prompt = f"Simulate a wget {action} for {payload.get('url', 'a file')}. Be concise."

        try:
            ai_response = self.llm(prompt, max_length=50, do_sample=True)[0]["generated_text"]
            ai_response = ai_response.strip()

            # Format response based on action
            if action == "wget_connect":
                return {"status": "success", "result": ai_response}
            elif action == "wget_download":
                return {"status": "success", "content": ai_response}
            elif action == "wget_error":
                return {"status": "success", "message": ai_response}
            else:
                return None
        except Exception as ex:
            log.msg(f"Local LLM query failed: {str(ex)}")
            return None

    
    def get_response(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main method called by wget.py to get AI-generated responses.
        Args:
            context: Dictionary containing command context (e.g., URL, user, stage).
        Returns:
            Dict with 'status' (success/error) and 'result' (AI-generated content).
        """
        try:
            stage = context.get('stage', 'connect')
            
            if stage == 'connect':
                return self._handle_connect_stage(context)
            elif stage == 'download':
                return self._handle_download_stage(context)
            elif stage == 'error':
                return self._handle_error_stage(context)
            else:
                return {
                    'status': 'error',
                    'result': f"Unknown stage: {stage}"
                }
                
        except Exception as ex:
            log.msg(f"AI Interactor Error: {str(ex)}")
            return {'status': 'error','result': None}


    def _handle_connect_stage(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate AI response for the initial connection stage.
        """
        url = context.get('url', 'unknown')
        host = context.get('host', 'unknown')
        
        # Example: Query AI service or use local logic
        ai_response = self._query_ai_service({
            'action': 'wget_connect',
            'url': url,
            'host': host
        })
        
        if ai_response and ai_response.get('status') == 'success':
            return {
                'status': 'success',
                'result': f"[AI] Connecting to {host} (simulated by AI)..."
            }
        else:
            # Fallback to local simulation
            return {
                'status': 'success',
                'result': f"Connecting to {host} ({self.faker.ipv4()})... connected."
            }


    def _handle_download_stage(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate AI response for the download simulation stage.
        """
        outfile = context.get('outfile', 'file.bin')
        mime_type = self.mime_type
        
        # AI could generate realistic file content here
        ai_response = self._query_ai_service({
            'action': 'wget_download',
            'outfile': outfile,
            'mime_type': mime_type
        })
        
        if ai_response and ai_response.get('content'):
            return {
                'status': 'success',
                'result': f"[AI] Downloading {outfile} ({mime_type})..."
            }
        else:
            return {
                'status': 'success',
                'result': f"Downloading {outfile} (simulated)..."
            }


    def _handle_error_stage(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate AI-enhanced error messages.
        """
        error_type = context.get('error_type', 'generic')
        
        # AI could suggest realistic error messages
        ai_response = self._query_ai_service({
            'action': 'wget_error',
            'error_type': error_type
        })
        
        if ai_response and ai_response.get('message'):
            return {
                'status': 'success',
                'result': f"[AI] Error: {ai_response['message']}"
            }
        else:
            # Fallback errors
            errors = {
                'timeout': "Connection timed out after 30 seconds.",
                'ssl_error': "SSL certificate verification failed.",
                'http_error': "404 Not Found"
            }
            return {
                'status': 'success',
                'result': errors.get(error_type, "Unknown error occurred.")
            }


    def generate_file_content(self, file_type: str) -> bytes:
        """
        Generate realistic fake content for simulated downloads.
        Args:
            file_type: File extension (e.g., 'exe', 'txt').
        Returns:
            Bytes of generated content.
        """
        if file_type == 'txt':
            return self.faker.text().encode()
        elif file_type == 'html':
            return f"<html><body>{self.faker.html()}</body></html>".encode()
        elif file_type == 'exe':
            return self._generate_fake_pe_file()
        else:
            return b'X' * 1024  # Default dummy data


    def _generate_fake_pe_file(self) -> bytes:
        """
        Generate a fake PE (Windows EXE) header for realism.
        """
        # Simulate a minimal PE header
        pe_header = (
            b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00'
            b'\xb8\x00\x00\x00\x00\x00\x00\x00@\x00\x00\x00\x00\x00\x00\x00'
        )
        return pe_header + bytes([random.randint(0, 255) for _ in range(128)])