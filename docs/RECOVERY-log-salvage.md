# Log Salvage Report

## Alert Payloads
**Command:**
```bash
jq -c 'select(.message | test("source_tool|component_id", "i"))' logs/app-*.log
```
**Output:**
(Empty)
Findings: The alert payloads are not logged in `app-*.log`.

## Correlation Decisions
**Command:**
```bash
jq -r 'select(.logger == "ace.correlation.engine" and (.message | test("joined|opened|candidate|score", "i"))) | .message' logs/app-*.log | sort | uniq -c
```
**Output:**
```
   2 Alert 08837a5b-7068-40cb-b8fe-abdb8833f2c7 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 0cda414a-092a-43e0-9fa8-69cf29ea3671 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 15124e73-c2b6-4f94-a34a-e1cc3365a005 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 1601a60e-6d6a-4aec-ac1b-d945d1b75bb6 joined Incident 0d16d64a-0490-43ac-a077-c2538f6f29c2. Reason: Score 2.00 >= 0.5
   2 Alert 278e2e06-c114-4a0b-b05a-fc5c028acb7f joined Incident 5f0851c3-99cf-4c90-bf00-6d14cf4dcf93. Reason: Score 2.00 >= 0.5
   2 Alert 2938a7d0-f211-4b3f-820e-f281709ddc7c opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 2bd6c1ee-fcbc-4bf7-8015-131cc69dd109 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 2d949330-e0d6-47ea-a2bf-f6b562ad2e5e opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 305f4a79-6d4c-4308-8317-d03bde35fdc7 joined Incident 5f0851c3-99cf-4c90-bf00-6d14cf4dcf93. Reason: Score 2.00 >= 0.5
   2 Alert 31bdbea7-6732-4ba6-b359-c9d2bd3fc0d5 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 55f223d8-24f7-413c-bf4a-4d9f487cf491 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 5a9b70e6-b4a2-4248-94aa-ea2c67453ed0 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 5c5293aa-494d-4cf2-a16a-5697ce125a64 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert 7f29bd62-64ef-4711-b5ab-57934ace7b95 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert a062c3c0-8291-47ce-9b6d-fa001235ffac opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert a2cf8f7b-ccf4-4ed1-a96a-39a30800954d joined Incident bbc5c0cd-bc0c-433b-8210-9177a41ec02e. Reason: Score 2.00 >= 0.5
   2 Alert a8fe035a-479f-4ee2-b27f-e448b1f40598 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert d04d8715-37c7-410b-be38-5de805a514c3 opened a new Incident. Reason: No suitable incident found or all candidates refused
   2 Alert e826b158-b633-4df4-a8c6-2c9c7d0d0e1b joined Incident db59db23-7a91-4716-ace4-99859f5188f6. Reason: Score 2.00 >= 0.5
   2 Alert eaee0f81-7925-4c09-b44c-9f6ab4a71391 joined Incident bbc5c0cd-bc0c-433b-8210-9177a41ec02e. Reason: Score 2.00 >= 0.5
```

## Containment Refusals
**Command:**
```bash
jq -c 'select(.logger == "ace.correlation.engine" and (.message | test("containment refusal", "i")))' logs/app-*.log
```
**Output:**
(Empty)
Findings: No containment refusal lines exist in app-*.log.
