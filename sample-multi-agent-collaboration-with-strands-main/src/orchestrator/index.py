
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

import json
from typing import Any
import boto3
import os
from tool_config import load_config_from_dynamodb, create_tool_specs, parse_decimals
import uuid
import time

MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"

sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')


ORCHESTRATION_TABLE = os.environ.get('ORCHESTRATION_TABLE')
WORKFLOW_STATE_TABLE = os.environ.get('WORKFLOW_STATE_TABLE')

SYSTEM_PROMPT = [{
    "text": "You are the manager for a universal fast food restaurant, you need to take in an order and delegate tasks until the order has been delivered. When calling tools, call as many as you can at once, if tasks can be parallelised then they should be. Once you get the initial order you may not ask the user more questions and must make up requirements if your tools request them."
}]


def create_workflow_tracking_record(nodes: list[str]):
    request_id = str(uuid.uuid4())
    if len(nodes) == 0:
        return

    item = {
        "requestId": request_id,
    }

    data = {}

    for node in nodes:
        item[node] = False
        data[node] = None

    item['data'] = data

    table = dynamodb.Table(WORKFLOW_STATE_TABLE)
    table.put_item(
        TableName=WORKFLOW_STATE_TABLE,
        Item=item
    )

    return request_id


def update_workflow_tracking(node: str, request_id: str, data: Any) -> bool:
    table = dynamodb.Table(WORKFLOW_STATE_TABLE)

    response = table.update_item(
        Key={
            "requestId": request_id
        },
        UpdateExpression="SET #node = :completed, #data.#node = :node_data",
        ExpressionAttributeNames={
            "#node": node,
            "#data": "data"
        },
        ExpressionAttributeValues={
            ":completed": True,
            ":node_data": data
        },
        ReturnValues="ALL_NEW"
    )

    updated_item = response.get("Attributes", {})
    all_completed = True

    for key, value in updated_item.items():
        if key not in ["requestId", "data"] and value is False:
            all_completed = False
            break

    return all_completed, response


def create_orchestration(conversation):
    instance = int(time.time())

    item = {
        'orchestrationId': str(uuid.uuid4()),
        'instance': instance,
        'conversation': conversation,
    }
    return item


def save_orchestration(orchestration):
    table = dynamodb.Table(ORCHESTRATION_TABLE)
    table.put_item(
        TableName=ORCHESTRATION_TABLE,
        Item=orchestration
    )


def load_orchestration(orchestration_id=None):
    if orchestration_id is None:
        return None
    else:
        table = dynamodb.Table(ORCHESTRATION_TABLE)
        response = table.get_item(Key={'orchestrationId': orchestration_id})
        return response['Item']


def process_tool_call(tools_config, orchestration, tool_name, tool_input, tool_use_id):
    tool_config = next(
        (tool for tool in tools_config['tools'] if tool['name'] == tool_name), None)

    if tool_config is None:
        print(f"Tool {tool_name} not found in configuration.")
        return

    action = tool_config["action"]
    action_type = action["type"]
    target = action["target"]
    payload = {
        "tool_input": tool_input,
        "orchestration_id": orchestration["orchestrationId"],
        "tool_use_id": tool_use_id,
        "node": tool_name
    }

    if action_type == "sqs":
        response = sqs.send_message(
            QueueUrl=target,
            MessageBody=json.dumps(payload)
        )
        return response


def invoke_tools_from_conversation(orchestration, tools_config):
    tool_ids = []
    output_message = orchestration["conversation"][-1]

    for content in output_message.get('content', []):
        if 'toolUse' in content:
            tool_use = content['toolUse']
            tool_ids.append(tool_use['name'])
            process_tool_call(
                tools_config,
                orchestration,
                tool_use['name'],
                tool_use['input'],
                tool_use['toolUseId']
            )
        elif 'text' in content:
            print("Text response from model: %s", content['text'])

    if len(tool_ids) > 0:
        request_id = create_workflow_tracking_record(tool_ids)
        orchestration["request_id"] = request_id


def update_orchestration_with_results(results, orchestration):
    tool_results = []
    data_to_save = results['Attributes']['data']

    for key in data_to_save:
        data = data_to_save[key]
        tool_result = {"toolResult": {
            "toolUseId": data['tool_use_id'],
            "content": [{"json": {'data': data['data']}}],
        }}
        tool_results.append(tool_result)

    orchestration["conversation"].append({
        "role": "user",
        "content": tool_results
    })


def orchestrate(initial_message=None, orchestration=None):
    if orchestration is None:
        orchestration = create_orchestration(conversation=[{
                "role": "user",
                "content": [{"text": initial_message}],
            }])

    tool_configs = load_config_from_dynamodb()

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=orchestration["conversation"],
        system=SYSTEM_PROMPT,
        inferenceConfig={
            "maxTokens": 2048,
            "temperature": 0,
        },
        toolConfig={
            "tools": create_tool_specs(tool_configs),
            # Allow model to automatically select tools
            "toolChoice": {"auto": {}}
        }
    )

    orchestration["conversation"].append(response['output']['message'])

    invoke_tools_from_conversation(
        orchestration, tool_configs
    )

    save_orchestration(orchestration=orchestration)



def handler(event, lambda_context):
    if 'source' in event and event['source'] == 'task.completion':
        orchestration_id = event['detail']['orchestration_id']
        try:
            orchestration = load_orchestration(orchestration_id)
        except Exception as e:
            print(f"Error loading orchestration: {e}")
            return
        request_id = orchestration['request_id']
        print(f"request id: {request_id}")
        node = event['detail']['node']
        all_completed, results = update_workflow_tracking(
            node, request_id, event['detail'])

        if (all_completed):
            update_orchestration_with_results(
                results=results, orchestration=orchestration)
            orchestrate(orchestration=parse_decimals(orchestration))

    elif 'detail' in event:
        # Handle new order
        orchestrate(json.dumps(event["detail"]))


if __name__ == "__main__":
    handler({
        "source": "meal.request",
        "DetailType": "Order-Placed",
        "detail": "{\"orderId\": \"12345\", \"customerId\": \"C-1234\", \"items\": [\"cheesecake\"]}",
        "EventBusName": "orchestration-bus"
    }, {})
