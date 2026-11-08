# Synthetic authoring acceptance fixture: complex
Evaluate the synthetic server deployment on OpenShift.
Use HTTP checks to validate the deployed components.
A frontend, API, worker and storage make up the synthetic setup.
The frontend calls the API, which sends work to the worker.
The worker stores results in a separate storage component.
Three HTTP checks passed.
Authenticated workflows and production reliability remain unproven.
Validate authenticated workflows before considering production use.
