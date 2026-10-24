## SECTION 1 : PROJECT TITLE
## ShopSteward — A Personal Operations Agent for Small Merchants

ISY5001 Intelligent Reasoning Systems · Practice Module · Group 40

---

## SECTION 2 : EXECUTIVE SUMMARY / PAPER ABSTRACT

A small shop pays for stock before it knows whether the quantity is right. The supplier's answer, the delivery, the sales, the settlement of proceeds and a revised demand estimate arrive over the following days, and each can make the order too small or too large. Current tools help at the moment of ordering; the days after it are left to an owner who is also serving customers.

ShopSteward is a personal operations agent for small merchants, built here as a purchasing assistant for one shop. The owner states a goal and its constraints once. The system forecasts demand, proposes a purchase for the owner to approve, follows the order until the goods arrive and re-plans whenever sales, deliveries or demand change. When a supplier fails, it reads the other suppliers' documents, compares every feasible recovery order and prepares the order message the owner sends. Algorithms compute every quantity and every amount of money. Language models read documents, interpret the owner's requests and explain results. The owner approves every purchase.

The system uses all four of the course's technique groups: business rules with event-driven re-planning, informed search and simulation-based optimisation, a demand-forecasting ensemble trained on public retail data, and language-model agents with bounded memory and document retrieval. It also improves itself from code-scored feedback, by post-training an open model and by evolving its own instructions.

Every experiment is scored by code; Table 4-16 and Figure 5-1 of the report collect the results. Re-planning on each update cut unmet demand by 45%. A language model decided 99.0% of ordering requests correctly against 61.5% for keyword rules, and post-training brought an 8B open model to 94.0%. The sourcing loop recovered from a supplier failure in 12 of 12 test worlds, and a delegated task survived restarts and resumed from timers and business events.

---

## SECTION 3 : CREDITS / PROJECT CONTRIBUTION

| Official Full Name | Student ID (MTech Applicable) | Work Items (Who Did What) |
| :--- | :---: | :--- |
| Ying Hao | A0326313N | Team leader; overall system design and the design of every part outside the other members' roles: architecture and backend, demand forecasting, planning search and recovery, multi-agent sourcing, agent runtime, context engineering and memory, learning loops and evaluation, experiments, report and system design video |
| Liu Kairui | A0353368W | Product lead: product definition (business loop, features and user experience) and how the agent works with the owner (when it appears, how it carries delegated work and how it hands back decisions for approval); technique analysis, scope, module requirements and milestones; frontend design and most of the owner-facing application; full-stack features (natural-language requests, reusable quotation rules); system testing before the demo recordings |
| Feng Tangyu | A0356670X | Model post-training (SFT and GRPO); cloud hosting of the RAG service, including the embedding models |
| Zhang Junming | A0355479L | Frontend architecture design and implementation for ShopSteward’s AI-assisted merchant workspace; integration of Agent conversations, tool execution progress, and human approval flows; end-to-end testing with real LLMs across restocking, supplier rejection, emergency sourcing, and delivery confirmation, validating consistency between AI responses and business records and identifying usability and reliability issues|

---

## SECTION 4 : VIDEO OF SYSTEM MODELLING & USE CASE DEMO

**Business & use case demo (promotion)**

[![ShopSteward business and use case demo](http://img.youtube.com/vi/F_eJIUC-ETU/0.jpg)](https://youtu.be/F_eJIUC-ETU "ShopSteward business and use case demo")

**System design**

[![ShopSteward system design](http://img.youtube.com/vi/3pUuZFNzfN4/0.jpg)](https://youtu.be/3pUuZFNzfN4 "ShopSteward system design")

---

## SECTION 5 : USER GUIDE

`Refer to appendix <Installation and User Guide> in project report at Github Folder: ProjectReport`
(also provided on its own as `ProjectReport/IRS-PM-2026-08-17-ISY5001-GRP-Group40-ShopSteward-User-Guide.pdf`)

### [ 1 ] Requirements

> Git · Python 3.12 with uv · Node.js 22 with Corepack · Docker Desktop · an OpenAI API key for the language-model features

### [ 2 ] Install (Windows PowerShell)

> $ git clone --branch submission https://github.com/yhnapoleon/ShopSteward.git

> $ Set-Location ShopSteward/SystemCode

> $ uv sync --frozen --all-packages --all-groups --python 3.12

> $ corepack pnpm install --frozen-lockfile

### [ 3 ] Configure, migrate and start

> Create `infra/.env`, `backend/.env`, `simulation/.env` and `frontend/.env` from their `.env.example` templates and fill in the fields listed in Table C-2 of the guide

> $ docker compose --env-file infra/.env -f infra/compose.yaml up -d --wait

> Apply the migrations in `backend` and `simulation` (`python -m alembic upgrade head`), then copy `infra/demo-mature.env.example` to `var/demo.env` and set the API key path

> $ .venv/Scripts/python.exe infra/start_windows.py --overlay var/demo.env

> **Go to URL using web browser** http://127.0.0.1:3000

macOS and Linux start commands, the optional forecast and knowledge services, and a walk-through of the four demonstration scenarios are in the guide.

---

## SECTION 6 : PROJECT REPORT / PAPER

`Refer to project report at Github Folder: ProjectReport`

- Executive Summary
- 1 Business Case, Market Research and Literature Review
- 2 System Design
- 3 System Development and Implementation
- 4 Experiments
- 5 Findings and Discussion
- References
- Appendix A: Project Proposal
- Appendix B: Mapped System Functionalities against MR, RS and CGS
- Appendix C: Installation and User Guide

---

## SECTION 7 : MISCELLANEOUS

`Refer to Github Folder: Miscellaneous`

### ShopSteward_Proposal_Group50.pdf
* The project proposal as submitted in September 2026, under the group number assigned at that time (the group is now Group 40)

### system-design-video-subtitles.srt
* English subtitles of the system design video, one cue per narration line

---
