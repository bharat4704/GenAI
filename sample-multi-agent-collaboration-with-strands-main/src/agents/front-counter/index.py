import base64
import json
import os
import boto3
from strands import Agent, tool, models
import time
from botocore.config import Config

bedrock_model = models.BedrockModel(
    model="anthropic.claude-3-5-sonnet-20241022-v2:0",
    max_tokens=40000,
    region_name="us-west-2"
)

DELIVERY_BUCKET = os.environ.get("DELIVERY_BUCKET", None)


def generate_image(image_generation_description):
    model_id = 'amazon.nova-canvas-v1:0'

    body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": image_generation_description
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": 1024,
            "width": 1024,
            "cfgScale": 8.0,
            "seed": 0
        }
    })

    bedrock = boto3.client(
        service_name='bedrock-runtime',
        config=Config(read_timeout=300),
        region_name="us-east-1"
    )

    accept = "application/json"
    content_type = "application/json"

    response = bedrock.invoke_model(
        body=body, modelId=model_id, accept=accept, contentType=content_type
    )
    response_body = json.loads(response.get("body").read())

    base64_image = response_body.get("images")[0]
    base64_bytes = base64_image.encode('ascii')
    image_bytes = base64.b64decode(base64_bytes)
    # save image to /tmp/
    filename = '/tmp/txt_to_img.png'
    with open(filename, 'wb') as f:
        f.write(image_bytes)
    return filename

@tool
def deliver_meal_to_customer(meal_contents, image_generation_description):
    """Creates a generated image of the food items and menu that have been ordered, delivers the meal_contents description as text and uses the image_generation_description to generate an image of it"""
    timestamp = str(int(time.time()))
    file_name = f"{timestamp}/ORDER.json"
    s3 = boto3.client('s3')
    s3.put_object(Bucket=DELIVERY_BUCKET, Key=file_name,
                  Body=json.dumps(meal_contents))

    file_name = generate_image(image_generation_description)
    file = open(file_name, 'rb')
    s3.put_object(Bucket=DELIVERY_BUCKET, Key=f"{timestamp}/" + file_name.split('/')[-1],
                  Body=file)

    print(f"Delivered meal to customer: {meal_contents}")

    return "Delivered to customer: " + meal_contents


def process_event(event):
    orchestration_id = event["orchestration_id"]
    tool_use_id = event["tool_use_id"]
    request = event["tool_input"]
    tool_name = event['node']

    # since this needs variable injection, keep within handler method scope.
    @tool
    def task_completion(meal_contents):
        client = boto3.client('events')
        COMPLETION_BUS_NAME = os.environ.get('COMPLETION_BUS_NAME')
        event = {
            'Source': 'task.completion',
            'DetailType': 'task.completion',
            'EventBusName': COMPLETION_BUS_NAME,
            'Detail': json.dumps({
                'orchestration_id': orchestration_id,
                'data': f"Front counter completed, delivered: {meal_contents}",
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
        tools=[deliver_meal_to_customer, task_completion]
    )

    instruction = f"""You work on the front counter and deliver food to the customer.
    When you get a meal ready notification, deliver the food to the customer.
    Finally, confirm the order was delivered.

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
        {'tool_input': {'mealReady': 'burger with fries'}, 'orchestration_id': 'ed3b70b6-37c6-47fa-8f50-4eac0908345e',
            'tool_use_id': 'tooluse_L9uWo8_KR4mT70-876lzSA'}
    )
