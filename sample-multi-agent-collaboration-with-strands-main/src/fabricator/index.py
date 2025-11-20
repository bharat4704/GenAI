import json
from typing import Any
from strands import Agent, tool, models
from strands_tools import file_write, http_request, shell
import os
import boto3
from botocore.config import Config

os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")

SYSTEM_PROMPT = """You are an expert python programmer.
Your task is to create me an AI agent, using strands to complete the below task.
    
You can use tools that are available here:

| Tool | Agent Usage | Use Case |
|------|-------------|----------|
| file_read | Reading configuration files, parsing code files, loading datasets
| file_write | Writing results to files, creating new files, saving output data
| editor | Advanced file operations like syntax highlighting, pattern replacement, and multi-file edits
| shell | Executing shell commands, interacting with the operating system, running scripts
| http_request | Making API calls, fetching web data, sending data to external services
| python_repl | Running Python code snippets, data analysis, executing complex logic with user confirmation for security
| calculator | Performing mathematical operations, symbolic math, equation solving
| use_aws | Interacting with AWS services, cloud resource management
| retrieve | Retrieving information from Amazon Bedrock Knowledge Bases
| nova_reels | Create high-quality videos using Amazon Bedrock Nova Reel with configurable parameters via environment variables
| mem0_memory | Store user and agent memories across agent runs to provide personalized experience
| memory | Store, retrieve, list, and manage documents in Amazon Bedrock Knowledge Bases with configurable parameters via environment variables
| environment | Managing environment variables, configuration management
| generate_image | Creating AI-generated images for various applications
| image_reader | Processing and reading image files for AI analysis
| journal | Creating structured logs, maintaining documentation
| think | Advanced reasoning, multi-step thinking processes
| load_tool | Dynamically loading custom tools and extensions
| swarm | Coordinating multiple AI agents to solve complex problems through collective intelligence
| current_time | Get the current time in ISO 8601 format for a specified timezone
| sleep | Pause execution for the specified number of seconds, interruptible with SIGINT (Ctrl+C)
| agent_graph | Create and visualize agent relationship graphs for complex multi-agent systems
| cron | Schedule and manage recurring tasks with cron job syntax
| slack | Interact with Slack workspace for messaging and monitoring
| speak | Output status messages with rich formatting and optional text-to-speech
| stop | Gracefully terminate agent execution with custom message
| use_llm | Create nested AI loops with customized system prompts for specialized tasks
| workflow | Define, execute, and manage multi-step automated workflows
| batch | Call multiple other tools in parallel.

you get these here:
from strands_tools import tool_name

e.g. 
from strands_tools import file_write
agent = Agent(tools=[file_write])

or write your own custom tool using the convention found here: 
https://github.com/strands-agents/sdk-python

The strong preference would be to use the available tools if they are appropriate before writing your own tool.
Another strong preference would be to invoke the agent with the text request and having it handle the request (and/or prompt) instead of invoking the tools directly.
    
an example strands agent template looks like this below, with the agent doing the work:
<example>
from strands import Agent
from strands_tools import calculator

def handler(x: int) -> int:
    \"""Calculate the square root of a number.
    \"""
    bedrock_model = models.BedrockModel(
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        region_name="us-west-2"
    )
    agent = Agent(model=bedrock_model, tools=[calculator])
    agent("What is the square root of " + x)
</example>

<example_with_custom_tool>
from strands import Agent, tool

@tool
def word_count(text: str) -> int:
    \"""Count words in text.
    \"""
    return len(text.split())

def handler(text: str) -> int:
    \"""Gets the word count of a passed in string
    \"""
    bedrock_model = models.BedrockModel(
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        region_name="us-west-2"
    )
    agent = Agent(model=bedrock_model, tools=[word_count])
    response = agent("How many words are in this sentence?")

</example_with_custom_tool>

Make sure the agent behaviour is wrapped in a function so it can be imported by another module.
For calculations, ensure you use a custom tool and deterministically calculate the results.
This does not need a UI and intended to be run as a single function imported into a large script.
When running use the /tmp/ directory its the only one you can write to.
The function that is called to run the agent MUST be called "handler"
You dont need to write any test files, just the single file for the agent is required.

Notes:

<model>
when creating the bedrock_model using  models.BedrockModel(
make sure the models import comes from the strands package and not anywhere else. e.g.: 
from strands import Agent, tool, models

</model>

finally, store the file in s3 and post the config to dynamodb.
from strands import Agent, tool, models

"""

# misc prompt content
#
# ensure the "handler" function follow the same convention as the best_example, with the task_completion function inside so it can access the variables from the event when the agent calls it.


@tool
def upload_file_to_s3(file_path):
    """Upload a file to S3"""
    s3 = boto3.client('s3')
    bucket_name = os.environ.get("AGENT_BUCKET_NAME", None)
    if bucket_name is None:
        raise ValueError("AGENT_BUCKET_NAME environment variable is not set")
    print(f"storing {file_path}")
    s3.upload_file(file_path, bucket_name, file_path.split("/")[-1])


@tool
def store_agent_config_dynamo(file_name: str, tool_id: str, llm_tool_schema: Any, agent_description: str):
    """Store agent configuration in DynamoDB.
    
    Requirements:
    - AGENT_CONFIG_TABLE_NAME environment variable must be set with the DynamoDB table name
    - DynamoDB table must use 'toolId' as the primary key
    
    Args:
        file_name (str): The filename where the tool implementation is stored
        tool_id (str): Unique identifier for the tool (used as primary key in DynamoDB)
        llm_tool_schema (Any): OpenAPI schema structure defining the tool's parameters
                               Must follow OpenAPI format with properties, required fields, and types
                               Example: {
                                 "properties": {
                                   "param_name": {
                                     "description": "Parameter description",
                                     "type": "string"
                                   }
                                 },
                                 "required": ["param_name"],
                                 "type": "object"
                               }
        agent_description (str): Human-readable description of what the tool does
        
    Returns:
        bool: True if configuration was successfully stored
        
    Raises:
        ValueError: If AGENT_CONFIG_TABLE_NAME environment variable is not set
    """
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ.get("TOOL_CONFIG_TABLE", None)
    if table_name is None:
        raise ValueError(
            "TOOL_CONFIG_TABLE environment variable is not set")

    # if llm_tool_schema is str then json loads it
    if isinstance(llm_tool_schema, str):
        llm_tool_schema = json.loads(llm_tool_schema)

    table = dynamodb.Table(table_name)
    table.put_item(
        Item={
            'toolId': tool_id,
            'config': {
                "name": tool_id,
                "filename": file_name.split('/')[-1],
                "schema": llm_tool_schema,
                "version": '0',
                "description": agent_description,
                "action": {
                    "type": "sqs",
                    "target": os.environ.get("GENERIC_QUEUE_URL", "MISSING")
                },
            }
        }
    )
    return True


def process_event(event, context):
    orchestration_id = event["orchestration_id"]
    tool_use_id = event["tool_use_id"]
    request = event["tool_input"]
    tool_name = event['node']

    TASK = request.get("taskDetails", None)

    bedrock_model = models.BedrockModel(
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        max_tokens=40000,
        region_name="us-west-2",
        boto_client_config=Config(read_timeout=3600),
    )

    # Put this in to make it self testing
    # make_it_run_code = "make sure you try to run the file and debug any issues it might have. You do not need to confirm the correct response, only that the file runs properly."

    # since this needs variable injection, keep within handler method scope.
    @tool
    def complete_task():
        """Finally, call this to indicate the task has been completed"""
        client = boto3.client('events')
        COMPLETION_BUS_NAME = os.environ.get('COMPLETION_BUS_NAME')
        event = {
            'Source': 'task.completion',
            'DetailType': 'task.completion',
            'EventBusName': COMPLETION_BUS_NAME,
            'Detail': json.dumps({
                'orchestration_id': orchestration_id,
                'data': f"Capability has been created, try to invoke it again.",
                'tool_use_id': tool_use_id,
                'node': tool_name
            })
        }
        print("Completed")

        response = client.put_events(
            Entries=[
                event
            ]
        )
        print(f"event posted: {response}")
        return f"event posted: {event}"

    agent = Agent(
        model=bedrock_model,
        tools=[file_write, http_request, shell,
            upload_file_to_s3, store_agent_config_dynamo, complete_task],
        system_prompt=SYSTEM_PROMPT
    )

    agent(TASK)


def lambda_handler(event, context):
    print(f"processing event {event}")
    for record in event['Records']:
        message_body = json.loads(record['body'])
        process_event(message_body, context)

if __name__ == "__main__":
    # Grab a record from your lambda and invoke, configuration will vary drastically
    process_event(
        {'tool_input': {'taskDetails': 'Create a capability to prepare and serve cheesecake dessert items'}, 'orchestration_id': 'ed3b70b6-37c6-47fa-8f50-4eac0908345e',
            'tool_use_id': 'tooluse_L9uWo8_KR4mT70-876lzSA', 'node': 'fabricator'}, {}
    )