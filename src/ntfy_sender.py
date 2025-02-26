import urllib.request
import base64
import logging
import os

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

class NTFY_Sender:
    """
    Sends notifications to a ntfy.sh topic.
    """
    def __init__(self,ntfy_token: str, ntfy_host: str,ntfy_topic: str):
        ntfy_auth = base64.b64encode(f"Bearer {ntfy_token}".encode()).decode("utf-8")
        self.url = f"https://{ntfy_host}/{ntfy_topic}?auth={ntfy_auth}"
    
    def send_message(self, title: str, message: str) -> int:
        headers = {
            "Title": title
        }
        data = message.encode("utf-8")
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req) as response:
                status_code = response.getcode()
                logger.info(f"Message sent successfully: {status_code}")
        except Exception as e:
            logger.error(f"Message was not sent, error occurred: {e.code} {e.reason}")
            return e.code
        
        return 0
