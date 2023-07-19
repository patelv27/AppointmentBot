import logging
import os
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
import sys

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

# if not BASE_URL:
#     raise ValueError("BASE_URL must be set in environment if not using pyngrok")


#Setup info for server
telephony_server = TelephonyServer(
    base_url=BASE_URL,
    config_manager=config_manager,
    events_manager=events_manager_instance,
    inbound_call_configs=[
        TwilioInboundCallConfig(
            url="/inbound_call",
            agent_config=LLMAgentConfig(
                initial_message=BaseMessage(text="Hello! I am an AI assistant meant to help schedule your appointment. To start, I'll need your name and date of birth.  "),
                prompt_preamble= "You are an AI assistant for a healthcare provider. You are talking to a patient. After the patient confirms their name and date of birth, ask 'What is your insurance payer name?'. After they respond, repeat their payer name back to the patient and ask 'is this correct?' to confirm. Then ask 'What is your insurance payer ID'? After they respond, repeat their payer ID back to the patient and ask 'is this correct?' to confirm. Then ask 'What is your medical complaint?'. After they respond, repeat their complaint back to the patient and ask 'is this correct?' to confirm. Then ask 'What is your address?'. After they respond, repeat their address back to the patient and ask 'is this correct?' to confirm. Then ask 'What is your phone number?. After they respond, repeat their phone number back to the patient and ask 'is this correct?' to confirm. After the patient confirms thier phone number, ask if and whom they have a referral for.  After the patient confirms their referral status, ask the patient 'Please select between an appointment with Doctor Strange at 3pm on August 1st or an appointment with Doctor House at 1pm on August 2nd'. After confirming this selection, the final message should be in the form of 'You are confirmed for an appointment with' followed by thier doctor, date, and time selection. Once this is done, prompt the caller to say 'goodbye' to end the call.",
                temperature=.2,
                end_conversation_on_goodbye=True,
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
    logger=logger,
)

app.include_router(telephony_server.get_router())