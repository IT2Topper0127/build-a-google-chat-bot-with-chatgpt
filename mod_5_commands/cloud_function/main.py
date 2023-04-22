import flask
import functions_framework
import logging
import google.cloud.logging
import openai
from auth_util import is_request_valid
import gpt_util
import datastore_util

# TODO: put in your own OpenAI API key
MY_API_KEY = "sk-xxxxxxxxxxxxxxxxxxx"

logging_client = google.cloud.logging.Client()
logging_client.setup_logging(log_level=logging.INFO)

@functions_framework.http
def handle_chat(request):
    """Handles incoming messages from Google Chat."""

    # verify request is from Google before doing anything
    if not is_request_valid(request):
        return "Unauthorized request"

    event_data = request.get_json()
    logging.info("received event_data %s" % event_data)
    event_type = event_data['type']

    # Bot added
    if event_type == 'ADDED_TO_SPACE':
        
        # Added to a room
        if event_data['space']['type'] == 'ROOM':
            return { "text" : f"Thanks for adding me to the room. "\
                    "Mention me in a conversation whenever you need help." }

        # Added to a DM
        elif event_data['space']['type'] == 'DM':
            user_display_name = event_data['user']['displayName']
            return { "text" : f"Hi {user_display_name}! I'm here to help "\
                     "whenever you need it."}

    # Bot removed
    elif event_type == 'REMOVED_FROM_SPACE':
        return {}


    # A normal message event
    elif event_type == 'MESSAGE':
        return process_message_event(event_data)


def process_message_event(event_data):
    """Processes message event."""

    incoming_message = event_data.get('message', {})
    user_text = incoming_message.get('argumentText', "")
    user_name = event_data['user']['name']
    user_id = user_name.split("/")[1]
    space_name = event_data['space']['name'].split("/")[1]
    space_type = event_data['space']['spaceType']

    # if this is a slash command, get the commandId
    command_id = None
    if "slashCommand" in incoming_message:
        command_id = int(incoming_message['slashCommand']['commandId'])

    # if this is a direct message to the bot, create our own thread_id
    # so we can store the history of messages
    thread_id = None
    if space_type == "DIRECT_MESSAGE":
        thread_id = "%s-%s" % (user_id, space_name)

    logging.info("user_text %s" % user_text)
    logging.info("thread_id: %s" % thread_id)
    logging.info("command_id %s" % command_id)
    
    openai.api_key = MY_API_KEY

    # /new
    if command_id == 1:
        guidance = "You are helpful assistant who has a cheerful attitude"
        return process_chat_message(user_text, thread_id, guidance)

    # /snark
    elif command_id == 2:
        guidance = "You are a snarky know-it-all that replies to any content "\
                    "by telling the actual truth of the matter. You usually "\
                    "start your reply with 'Actually...'"
        return process_chat_message(user_text, thread_id, guidance)

    # /poet
    elif command_id == 3:
        guidance = "You are an esteemed poet that replies to any request "\
                    "using a rhyming poem"
        return process_chat_message(user_text, thread_id, guidance)

    else: 
        return process_chat_message(user_text, thread_id)


def process_chat_message(user_text, thread_id, guidance=None):
    """Processes message from user using ChatGPT.

    Retrieves previous messages for context if not starting a new thread.
    """

    messages = []

    # if guidance provided, starting new conversation 
    if guidance:
        messages.append({"role": "system", "content" : guidance})
    else:
        # otherwise get previous messages, because continuing converation
        thread_obj = datastore_util.get_thread(thread_id)

        if thread_obj:
            messages = thread_obj.get_messages()
    
    # add new message to list
    messages.append( {"role": "user", "content": user_text} )

    # get new gpt response
    try:
        gpt_response = gpt_util.get_gpt_response(messages)
    except openai.error.OpenAIError as e:
        return { "text" : str(e)}

    # add new response to message history and store it
    if thread_id:
        messages.append( {"role": "assistant", "content": gpt_response} )
        datastore_util.store_messages(thread_id, messages)

    chat_response = { 
        "text" : gpt_response
    }

    logging.info("chat_response: %s" % chat_response)

    return chat_response