import json
import random
import time
from typing import Dict, Any, Optional
from utils.logger import get_logger
from transformers import pipeline
from faker import Faker
#wget consumer mime type verip cagirmali
#consumeri var zaten bu dosyanin icinde consumer cagirilmayacak

class AiInteractorWgetAgent:

    def __init__(self, mime_type: str = 'text/plain'):
        self.categories = {
            "get_response": 
                """Main method called by wget.py to get AI-generated responses.
                Args:
                context: Dictionary containing command context (e.g., URL, user, stage).
                Returns:Dict with 'status' (success/error) and 'result' (AI-generated content).""",
            "generate_file_content": 
                """Generate realistic fake content for simulated downloads.
                Args:
                    file_type: File extension (e.g., 'exe', 'txt').
                Returns:
                    Bytes of generated content.
                """}
        self.mime_type = mime_type
        self.logger = get_logger("wget-logger")
        self.faker = Faker()
        self.llm = pipeline("text-generation", model="distilgpt2", device="cpu")
    
    
    def _query_ai_service(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        action = payload.get("action")
        # Format response based on action
        #pass edilicek action in bu uc state uyumlu olmasina dikkat et
        if action == "wget_connect":
            prompt = f"""
            Generate a realistic wget terminal output for connecting to {payload.get('host', 'a host')}.
            The output should look exactly like real wget connection progress.
            Example: 'Connecting to example.com (93.184.216.34:443)... connected.'
            Output only the terminal message, nothing else:
            """
        elif action == "wget_download":
            prompt = f"""
            Generate a realistic wget download progress output for {payload.get('outfile', 'a file')}.
            Include percentage, speed, and ETA like real wget.
            Example: '100%[=================>] 1.2M  1.5MB/s  00:01'
            Output only the terminal message, nothing else:
            """
        elif action == "wget_error":
            error_type = payload.get('error_type', 'generic')
            prompt = f"""
            Generate a realistic wget error message for {error_type} error.
            Make it look like real terminal error output.
            Example: 'wget: unable to resolve host address example.com'
            Output only the terminal message, nothing else:
            """
        else:
            return None
        try:
            ai_response = self.llm(prompt, max_new_tokens=50, temperature=0.2)[0]["generated_text"]
            ai_response = ai_response.replace(prompt, "").strip()

            if action == "wget_connect":
                return {"status": "success", "result": ai_response}
            elif action == "wget_download":
                return {"status": "success", "content": ai_response}
            elif action == "wget_error":
                return {"status": "success", "message": ai_response}
            else:
                return None

        except Exception as ex:
            self.logger.error(f"Local LLM query failed: {str(ex)}")
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
            
            #getattr ile de yapilabilir ama bosverelim
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
            self.logger.error(f"AI Interactor Error: {str(ex)}")
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
                'result': ai_response['result']
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
                'result': ai_response['content']
            }
        else:
            return {
                'status': 'success',
                'result': '100%[=================>] 1.2M  1.5MB/s  00:01'
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
                'result': ai_response['message']
            }
        else:
            # Fallback errors
            errors = {
                'timeout':  "wget: download timed out",
                'ssl_error':  "wget: SSL certificate problem: unable to get local issuer certificate",
                'http_error': "wget: server returned error: HTTP/404 Not Found",
                'resolve_error': "wget: unable to resolve host address"
            }
            return {
                'status': 'success',
                'result': errors.get(error_type, "Unknown error occurred.")
            }


if __name__ == "__main__":
    wget_agent = AiInteractorWgetAgent()
    test_payload_download = {
    "action": "wget_download", 
    "url": "https://example.com/file.txt",
    "outfile": "downloaded_file.txt",
    "mime_type": "text/plain"
    }
    wget_agent._query_ai_service(test_payload_download)