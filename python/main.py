import logging
import os
import sys
from fastapi import FastAPI
from vocode.streaming.models.telephony import TwilioConfig
from pyngrok import ngrok
from vocode.streaming.models.transcriber import DeepgramTranscriberConfig, PunctuationEndpointingConfig
from vocode.streaming.telephony.config_manager.redis_config_manager import (
    RedisConfigManager,
)
from vocode.streaming.models.agent import ChatGPTAgentConfig, InformationRetrievalAgentConfig, LLMAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.utils import goodbye_embeddings
from vocode.streaming.telephony.server.base import (
    TwilioInboundCallConfig,
    TelephonyServer,
)
from custom_event_manager import CustomEventsManager
from custom_agent import CustomAgentFactory
from custom_agent import CustomAgentConfig

# if running from python, this will load the local .env
# docker-compose will load the .env file by itself
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(docs_url=None)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

config_manager = RedisConfigManager()


BASE_URL = os.getenv("BASE_URL")

#Use custom event manager to send SMS after phone call completion
events_manager_instance = CustomEventsManager()


#Setup ngrok tunnel to self-host 
if not BASE_URL:
    ngrok_auth = os.environ.get("NGROK_AUTH_TOKEN")
    if ngrok_auth is not None:
        ngrok.set_auth_token(ngrok_auth)
    port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else 3000

    # Open a ngrok tunnel to the dev server
    BASE_URL = ngrok.connect(port).public_url.replace("https://", "")
    logger.info('ngrok tunnel "{}" -> "http://127.0.0.1:{}"'.format(BASE_URL, port))



#Setup info for server
telephony_server = TelephonyServer(
    base_url=BASE_URL,
    config_manager=config_manager,
    events_manager=events_manager_instance,
    inbound_call_configs=[
        TwilioInboundCallConfig(
            url="/inbound_call",
            agent_config=CustomAgentConfig(
                initial_message=BaseMessage(text="Hello! I am an AI assistant meant to help schedule your appointment. To start, say your name.  "),
                prompt_preamble = "You are an AI assistant for a healthcare provider. You are talking to a patient. You are meant to collect a info about a patient. Once the patient confirms, say 'Ok, your' type of info 'is confirmed'. You will ask for what the human says ask for. Do not ask about referral status until the human brings it up. When the human confirms whether they have a referral, say 'Your referral status is confirmed'. After all the info is collected, repeat their appointment confirmation by saying the exact phrase 'You are confirmed for an appointment' with the doctor and time slot they chose. Finally, prompt the user to say goodbye.",
                temperature=.1,
                end_conversation_on_goodbye=True,
                generate_response=True,
                model_name='text-davinci-003'),
            twilio_config=TwilioConfig(
                account_sid=os.environ['TWILIO_ACCOUNT_SID'],
                auth_token=os.environ['TWILIO_AUTH_TOKEN'],
                record=True
            ),
            transcriber_config=DeepgramTranscriberConfig.from_telephone_input_device(
                endpointing_config=PunctuationEndpointingConfig()
    ),
        )
    ],
    agent_factory=CustomAgentFactory(),
    logger=logger,
    
)

app.include_router(telephony_server.get_router())