"""A file to load data into the tools config for DynamoDB, replace the sqs queues with your ones that have been deployed"""
import os
import boto3
from dotenv import load_dotenv
load_dotenv()

ACCOUNT_ID = boto3.client('sts').get_caller_identity().get('Account')
TOOL_CONFIG_TABLE = os.environ.get('TOOL_CONFIG_TABLE')
dynamodb = boto3.resource('dynamodb')
# 450068336095
table = dynamodb.Table(TOOL_CONFIG_TABLE)

TOOL_EXAMPLES = [
    {
    "name": "cook_burger",
    "description": "Cooks the burger that has been request, delivers the burger back to you to be sent out.",
    "action": {
        "type": "sqs",
        "target": f"https://sqs.ap-southeast-2.amazonaws.com/{ACCOUNT_ID}/burger-cook"
    },
    "schema": {
        "type": "object",
        "properties": {
            "burgerOrder": {
                "type": "string",
                "description": "A description of the burger that needs to be cooked"
            }
        },
        "required": ["burgerOrder"]
    }
},
    {
    "name": "fry_fries",
        "description": "Fries up an order of fries.",
        "action": {
            "type": "sqs",
            "target": f"https://sqs.ap-southeast-2.amazonaws.com/{ACCOUNT_ID}/fry-cook"
        },
    "schema": {
            "type": "object",
            "properties": {
                "friesSize": {
                    "type": "string",
                    "description": "The size of the fries that need to be ordered. Default is M but can also be S or L"
                }
            },
            "required": ["friesSize"]
        }
},
    {
    "name": "front_counter",
        "description": "Serves the meal to the customer. Can only serve food AFTER it has been prepared.",
        "action": {
            "type": "sqs",
            "target": f"https://sqs.ap-southeast-2.amazonaws.com/{ACCOUNT_ID}/front-counter"
        },
    "schema": {
            "type": "object",
            "properties": {
                "mealDetails": {
                    "type": "string",
                    "description": "The details of the meal being served to the customer."
                }
            },
            "required": ["mealDetails"]
        }
    },
    # TODO: change the name, might be confusing
    {
        "name": "fabricator",
        "description": "Creates a capability that may be missing from the set of available tools.",
        "action": {
            "type": "sqs",
            "target": f"https://sqs.ap-southeast-2.amazonaws.com/{ACCOUNT_ID}/fabricator-queue"
        },
        "schema": {
            "type": "object",
            "properties": {
                "taskDetails": {
                    "type": "string",
                    "description": "A detailed task description for what the task should entail"
                }
            },
            "required": ["taskDetails"]
        }
}
]

for tool in TOOL_EXAMPLES:
    print(f"adding {tool}")
    table.put_item(Item={
        'toolId': tool['name'],
        'config': tool
    })

