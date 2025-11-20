#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { OrchestratorStack } from '../lib/orchestrator-stack';
import { AgentResourcesStack } from '../lib/agent-resources-stack';

const app = new cdk.App();

const orchestratorStack = new OrchestratorStack(app, 'OrchestratorStack');
new AgentResourcesStack(app, "AgentsStack", {
  completionEventBus: orchestratorStack.orchestrationEventBus
})