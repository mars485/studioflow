import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {expect, it} from 'vitest';

const workflow = JSON.parse(readFileSync(resolve('public/integration-templates/itg-website-intake.draft.json'), 'utf8'));

it('ships an inactive draft with separated placeholder credentials and a non-routable destination', () => {
  expect(workflow.active).toBe(false);
  expect(workflow.pinData).toEqual({});
  const source = workflow.nodes.find((node: {type: string}) => node.type === 'n8n-nodes-base.webhook');
  const target = workflow.nodes.find((node: {type: string}) => node.type === 'n8n-nodes-base.httpRequest');
  expect(source.parameters.authentication).toBe('headerAuth');
  expect(source.credentials.httpHeaderAuth.id).toBe('CONFIGURE_ITG_SOURCE_HEADER_CREDENTIAL');
  expect(target.credentials.httpHeaderAuth.id).toBe('CONFIGURE_STUDIOFLOW_LEAD_CREDENTIAL');
  expect(new URL(target.parameters.url).hostname).toBe('studioflow.invalid');
  expect(new URL(target.parameters.url).pathname).toBe('/api/v1/integrations/website-leads');
  expect(target.parameters.options.redirect.redirect.followRedirects).toBe(false);
  expect(target.parameters.options.timeout).toBe(10000);
  expect(target.parameters.headerParameters.parameters).toEqual([{name: 'X-StudioFlow-Request', value: '1'}]);
  expect(target.parameters.jsonBody).toBe('={{ $json.body }}');
  expect(target.retryOnFail).toBe(true);
  expect(target.maxTries).toBe(3);
  expect(JSON.stringify(workflow)).not.toMatch(/sf_lead_|Bearer |MODX_API_TOKEN|N8N_API_KEY/);
});

it('acknowledges only after CRM success and does not persist execution payloads', () => {
  const [source, target, guard, ack] = workflow.nodes;
  expect(workflow.connections[source.name].main[0][0].node).toBe(target.name);
  expect(workflow.connections[target.name].main[0][0].node).toBe(guard.name);
  expect(workflow.connections[guard.name].main[0][0].node).toBe(ack.name);
  expect(target.continueOnFail).toBeUndefined();
  expect(target.onError).toBeUndefined();
  expect(ack.parameters.responseBody).not.toMatch(/website_context|client_id|deal_id|contact_text|\$json\.body/);
  expect(workflow.settings.saveDataErrorExecution).toBe('none');
  expect(workflow.settings.saveDataSuccessExecution).toBe('none');
  expect(workflow.settings.saveManualExecutions).toBe(false);
  expect(workflow.settings.saveExecutionProgress).toBe(false);
});

it('executes the draft receipt guard without network access and refuses mismatched success responses', () => {
  const guard = workflow.nodes.find((node: {type: string}) => node.type === 'n8n-nodes-base.code');
  const run = new Function('$input', '$', guard.parameters.jsCode);
  const key = 'b9c9edf2-d2b4-4f3b-9cd1-533b805eb467';
  const id = 'a5473d94-13c7-405b-8a88-b7fcd9c5bf67';
  const source = () => ({first: () => ({json: {body: {request_key: key}}})});
  const receipt = {id, request_key: key, replayed: true, website_context: {contact_text: 'not for acknowledgement'}};
  expect(run({all: () => [{json: receipt}]}, source)).toEqual([{json: {id, request_key: key, replayed: true}}]);
  for (const value of [{}, {...receipt, request_key: id}, {...receipt, id: 'invalid'}, {...receipt, replayed: 'true'}]) {
    expect(() => run({all: () => [{json: value}]}, source)).toThrow('Invalid StudioFlow receipt');
  }
});
