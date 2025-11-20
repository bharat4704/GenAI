import { Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { EventBus } from 'aws-cdk-lib/aws-events';
import { PythonFunction } from '@aws-cdk/aws-lambda-python-alpha';
import { PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import path = require('path');
import { BlockPublicAccess, Bucket } from 'aws-cdk-lib/aws-s3';

interface AgentResourcesStackProps extends StackProps {
  readonly completionEventBus: EventBus;
}

export class AgentResourcesStack extends Stack {
  public readonly queues: sqs.Queue[] = [];
  public readonly functions: PythonFunction[] = [];

  constructor(scope: Construct, id: string, props: AgentResourcesStackProps) {
    super(scope, id, props);

    const agentNames = ['burger-cook', 'fry-cook', 'front-counter'];

    const delivery_bucket = new Bucket(this, 'DeliveryBucket', {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
    });

    agentNames.forEach((agentName) => {
      const queue = new sqs.Queue(this, `${agentName}Queue`, {
        queueName: agentName,
        visibilityTimeout: Duration.minutes(15),
        retentionPeriod: Duration.days(7),
      });
      this.queues.push(queue);

      const func = new PythonFunction(this, `${agentName}Function`, {
        runtime: lambda.Runtime.PYTHON_3_11,
        entry: path.join(__dirname, `../../src/agents/${agentName}`),
        handler: 'handler',
        memorySize: 1024,
        timeout: Duration.minutes(15),
        environment: {
          COMPLETION_BUS_NAME: props.completionEventBus.eventBusName,
          DELIVERY_BUCKET: delivery_bucket.bucketName,
        },
        initialPolicy: [
          new PolicyStatement({
            effect: Effect.ALLOW,
            actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
            resources: ['*'],
          }),
        ],
      });
      props.completionEventBus.grantPutEventsTo(func);
      func.addEventSource(new SqsEventSource(queue));
      delivery_bucket.grantReadWrite(func);
    });
  }
}
