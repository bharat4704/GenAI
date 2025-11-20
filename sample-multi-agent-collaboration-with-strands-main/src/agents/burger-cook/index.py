import json
import os
import boto3
from strands import Agent, tool, models


bedrock_model = models.BedrockModel(
    model="anthropic.claude-3-5-sonnet-20241022-v2:0",
    max_tokens=40000,
    region_name="us-west-2"
)


@tool
def get_lettuce():
    return "lettuce"


@tool
def get_tomato():
    return "tomato"


@tool
def get_bacon():
    return "bacon"


@tool
def get_cheese():
    return "cheese"


@tool
def get_beef_patty():
    return "beef_patty"


@tool
def get_burger_bun():
    return "burger_bun"


@tool
def assemble_burger(ingredients):
    return "burger: " + ", ".join(ingredients)


def process_event(event):
    orchestration_id = event["orchestration_id"]
    tool_use_id = event["tool_use_id"]
    request = event["tool_input"]
    tool_name = event['node']

    # since this needs variable injection, keep within handler method scope.
    @tool
    def deliver_meal(meal_contents):
        client = boto3.client('events')
        COMPLETION_BUS_NAME = os.environ.get('COMPLETION_BUS_NAME')
        event = {
            'Source': 'task.completion',
            'DetailType': 'task.completion',
            'EventBusName': COMPLETION_BUS_NAME,
            'Detail': json.dumps({
                'orchestration_id': orchestration_id,
                'data': f"Burger cooking completed, delivered: {meal_contents}",
                'tool_use_id': tool_use_id,
                'node': tool_name
            })
        }

        response = client.put_events(
            Entries=[
                event
            ]
        )
        print(f"event posted: {response}")
        return f"event posted: {event}"


    agent = Agent(
        model=bedrock_model,
        tools=[
            get_lettuce, get_tomato, get_bacon, get_cheese,
            get_beef_patty, get_burger_bun,
            assemble_burger, deliver_meal]
    )

    instruction = f"""You are a burger cook. You call the tools aligned to the ingredients in the burger recipe to provision the ingredients.
    Finally you compile the burger with the ingredients together.

    The current order is: {request}
    """
    agent(instruction)


def handler(event, context):
    print(f"processing event {event}")
    for record in event['Records']:
        message_body = json.loads(record['body'])
        process_event(message_body)


if __name__ == "__main__":
    # Grab a record from your lambda and invoke, configuration will vary drastically
    process_event(
        {'tool_input': {'burgerOrder': 'burger'}, 'orchestration_id': 'ed3b70b6-37c6-47fa-8f50-4eac0908345e',
            'tool_use_id': 'tooluse_L9uWo8_KR4mT70-876lzSA'}
    )
