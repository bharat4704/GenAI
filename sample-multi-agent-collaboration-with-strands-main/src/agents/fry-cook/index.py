import json
import os
import boto3
from strands import Agent, tool, models
from strands_tools import current_time

bedrock_model = models.BedrockModel(
    model="anthropic.claude-3-5-sonnet-20241022-v2:0",
    max_tokens=40000,
    region_name="us-west-2"
)

@tool
def wait_time(seconds: int):
    import time
    time.sleep(seconds)


@tool
def box_fries():
    print("Boxing the fries.")
    return "fries boxed"


@tool
def dip_fries():
    print("Dipping the fries.")
    return "fries dipped in oil"


@tool
def raise_fries():
    print("Raising the fries out of the oil.")
    return "fries raised"


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
                'data': f"Fry cooking completed, delivered: {meal_contents}",
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
        tools=[current_time, wait_time, box_fries,
               dip_fries, raise_fries, deliver_meal]
    )

    instruction = f"""You are a fry cook.
    You prepare the fries:
    You must first dip the fries and then 5 seconds later,
    Raise the fries out of the oil.
    box the fries.
    Then deliver the meal.

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
        {'tool_input': {'friesOrder': 'fries'}, 'orchestration_id': 'ed3b70b6-37c6-47fa-8f50-4eac0908345e',
            'tool_use_id': 'tooluse_L9uWo8_KR4mT70-876lzSA'}
    )
