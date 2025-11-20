import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { PythonFunction } from '@aws-cdk/aws-lambda-python-alpha';
import { PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as events from 'aws-cdk-lib/aws-events';
import path = require('path');
import { Queue } from 'aws-cdk-lib/aws-sqs';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { BlockPublicAccess, Bucket } from 'aws-cdk-lib/aws-s3';
// import * as sqs from 'aws-cdk-lib/aws-sqs';

export class OrchestratorStack extends cdk.Stack {
  public readonly orchestrationTable: dynamodb.Table;
  public readonly orchestrationEventBus: cdk.aws_events.EventBus;
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const code_bucket = new Bucket(this, 'CodeBucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
    });

    this.orchestrationTable = new dynamodb.Table(this, 'OrchestrationTable', {
      partitionKey: { name: 'orchestrationId', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    const workflowStateTable = new dynamodb.Table(this, 'WorkflowStateTable', {
      partitionKey: { name: 'requestId', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    const toolConfigTable = new dynamodb.Table(this, 'ToolConfigTable', {
      partitionKey: { name: 'toolId', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    this.orchestrationEventBus = new cdk.aws_events.EventBus(this, 'OrchestrationEventBus', {
      eventBusName: 'orchestration-bus',
    });

    const orchestrationLambda = new PythonFunction(this, 'OrchestrationAgent', {
      runtime: lambda.Runtime.PYTHON_3_11,
      entry: path.join(__dirname, '../../src/orchestrator'),
      handler: 'handler',
      timeout: cdk.Duration.seconds(30),
      memorySize: 1024,
      environment: {
        ORCHESTRATION_TABLE: this.orchestrationTable.tableName,
        COMPLETION_BUS_NAME: this.orchestrationEventBus.eventBusName,
        WORKFLOW_STATE_TABLE: workflowStateTable.tableName,
        TOOL_CONFIG_TABLE: toolConfigTable.tableName,
      },
      initialPolicy: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['bedrock:InvokeModel'],
          resources: ['*'],
        }),
        // Crazy high permissions. Might need to split the stacks for specific permission, or maybe some sort of sqs name/domain scoping
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['sqs:SendMessage', 'sqs:ReceiveMessage', 'sqs:DeleteMessage'],
          resources: ['*'],
        }),
      ],
    });

    this.orchestrationTable.grantReadWriteData(orchestrationLambda);
    this.orchestrationEventBus.grantPutEventsTo(orchestrationLambda);
    workflowStateTable.grantReadWriteData(orchestrationLambda);
    toolConfigTable.grantReadData(orchestrationLambda);

    const genericQueue = new Queue(this, `genericQueue`, {
      queueName: 'generic-queue',
      visibilityTimeout: cdk.Duration.minutes(15),
      retentionPeriod: cdk.Duration.days(7),
    });

    const genericLambda = new PythonFunction(this, 'GenericAgentWrapper', {
      runtime: lambda.Runtime.PYTHON_3_11,
      entry: path.join(__dirname, '../../src/generic-agent-wrapper'),
      handler: 'lambda_handler',
      timeout: cdk.Duration.minutes(15),
      memorySize: 1024,
      environment: {
        COMPLETION_BUS_NAME: this.orchestrationEventBus.eventBusName,
        TOOL_CONFIG_TABLE: toolConfigTable.tableName,
        AGENT_BUCKET_NAME: code_bucket.bucketName,
      },
      initialPolicy: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
          resources: ['*'],
        }),
      ],
    });

    this.orchestrationEventBus.grantPutEventsTo(genericLambda);
    toolConfigTable.grantReadData(genericLambda);
    code_bucket.grantRead(genericLambda);

    genericLambda.addEventSource(new SqsEventSource(genericQueue));

    const fabricatorQueue = new Queue(this, `fabricatorQueue`, {
      queueName: 'fabricator-queue',
      visibilityTimeout: cdk.Duration.minutes(15),
      retentionPeriod: cdk.Duration.days(7),
    });

    const fabricatorLambda = new PythonFunction(this, 'FabricatorAgent', {
      runtime: lambda.Runtime.PYTHON_3_11,
      entry: path.join(__dirname, '../../src/fabricator'),
      handler: 'lambda_handler',
      timeout: cdk.Duration.minutes(15),
      memorySize: 1024,
      environment: {
        COMPLETION_BUS_NAME: this.orchestrationEventBus.eventBusName,
        WORKFLOW_STATE_TABLE: workflowStateTable.tableName,
        TOOL_CONFIG_TABLE: toolConfigTable.tableName,
        AGENT_BUCKET_NAME: code_bucket.bucketName,
        GENERIC_QUEUE_URL: genericQueue.queueUrl,
      },
      initialPolicy: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['bedrock:*'],
          resources: ['*'],
        }),
      ],
    });

    this.orchestrationEventBus.grantPutEventsTo(fabricatorLambda);
    workflowStateTable.grantReadWriteData(fabricatorLambda);
    toolConfigTable.grantReadWriteData(fabricatorLambda);
    code_bucket.grantReadWrite(fabricatorLambda);

    fabricatorLambda.addEventSource(new SqsEventSource(fabricatorQueue));

    const mealRequestRule = new events.Rule(this, 'MealRequestRule', {
      eventBus: this.orchestrationEventBus,
      eventPattern: {
        source: ['meal.request'],
      },
    });

    const completionRule = new events.Rule(this, 'TaskCompletionRule', {
      eventBus: this.orchestrationEventBus,
      eventPattern: {
        source: ['task.completion'],
      },
    });

    mealRequestRule.addTarget(new targets.LambdaFunction(orchestrationLambda));
    completionRule.addTarget(new targets.LambdaFunction(orchestrationLambda));
  }
}
