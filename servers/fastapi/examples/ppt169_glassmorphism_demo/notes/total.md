# 01_cover

Hello everyone, and welcome to this technical presentation. Today’s topic is the engineering and deployment of AI Agents—in other words, we won’t discuss new models or new papers. We’ll focus on one thing: how to move Agents that can run in demos into real production environments.

---

# 02_hero_demo_to_prod

Let's start with a somewhat uncomfortable fact. In my conversations with many teams, roughly 90% of Agent projects ultimately stall at the demo stage. The problem is neither insufficiently powerful models nor weak ideas. To reach production, four engineering hurdles must be cleared—architecture, context, evaluation, and observability. Miss even one, and a demo can remain a demo forever.

---

# 03_three_pains

The first challenge is unstable performance. As multiple reasoning steps accumulate, fluctuations of five to ten percentage points at each step can cause the overall success rate to fall off a cliff, while P95 latency often increases five- to tenfold. The second is unpredictable cost. For the same task, token consumption can vary five- to fiftyfold across different context lengths, with long-tail tasks especially likely to blow through the budget. The third is the lack of a closed-loop quality process. It is often unclear whether a failure comes from the model, the prompt, or the data, and without regression testing, every prompt change feels like a gamble. These are the three hurdles that most projects encounter first.

---

# 04_agent_architecture

Next, let’s look at the standard Agent architecture. It can basically be divided into four layers. At the top is the perception layer, responsible for input parsing, multimodal fusion, and context-window management. The second is the reasoning layer, which handles decision-making paradigms such as Plan, ReAct, Tree-of-Thought, and Reflection. The third is the action layer, translating the model’s decisions into tool calls, function execution, and API orchestration. At the bottom is the memory layer, including short-term context, long-term vector stores, and task-level caches. Each layer has its own engineering pitfalls, but with the right framework, every layer can be refined and replaced independently.

---

# 05_three_modes

After understanding the four-layer skeleton, the next common question is: which mode should you use? Simply put, there are three. Workflow is a fixed-path DAG where the LLM only fills in the blanks—predictable, easy to debug, and suitable for deterministic tasks. Agent has a dynamic path, letting the model decide the next step at runtime. It is the most common approach and what most projects actually do, making it suitable for semi-structured exploratory tasks. Multi-Agent involves collaboration among multiple roles, splitting Planner, Critic, and Worker into concurrent collaborators. It offers the most flexibility but also the highest complexity, so use it only when truly long-horizon tasks are needed. For the vast majority of production scenarios, starting with Agent is enough.

---

# 06_tool_orchestration

Once the pattern is settled, the first thing to build is tool orchestration. A stable tool call generally has six steps: parse the task, select a tool, call and execute it, verify the response, retry or fall back when necessary, and finally synthesize the results. Every step must be observable, and every step needs a safety net. The most common failure point is not the first step but the fourth—people often feed the tool’s response straight back to the model, skipping schema validation and business-rule checks. That is where hallucinations slip in.

---

# 07_context_engineering

After style itself, this page is, in my view, the most important one: context engineering. Models change every day, and prompts are constantly being adjusted, but what truly determines whether an Agent is intelligent is what it sees at each step—in other words, its context. Around this core, at least six things need to be done well: retrieval must be reliable, reranking precise, truncation selective, memory divided into short- and long-term, tool descriptions specific enough, and system prompts clear about persona, output format, and safety rules. If context engineering is poorly done, even a powerful model cannot be saved.

---

# 08_kpi_dashboard

Next, let’s switch to an operations perspective. To move into production, you need to equip yourself with four gauges. The first is task success rate. This system is currently running at 92.4%, still improving by 3 percentage points per week. The second is P95 latency, which has converged from over 11 seconds in the initial version to 4.8 seconds. The third is per-task cost. After implementing model-tier routing and retrieval-result caching, we brought the cost down to ¥0.42 per task. The fourth is the 30-day SLO attainment rate, currently at 99.7%, with multi-model fallback absorbing upstream incidents. Without these four numbers, don’t talk about going into production.

---

# 09_metrics_trend

Put these four metrics on a timeline, and you can see a very real curve. Green is task success rate, climbing from 71% at the beginning to 92.4%. Red is per-task cost, falling from 1.2 to 0.42. The three most important turning points are marked on the chart: in Week 4, introducing a reranker lifted accuracy by a full tier; in Week 8, introducing a fallback brought down both the cost and failure rate of long-tail tasks; in Week 11, introducing result caching delivered the biggest cost reduction. Every improvement came from a specific engineering action—not luck and not a model switch.

---

# 10_failure_modes

Let's talk about the failures we may encounter. They can broadly be divided into four quadrants. The upper left covers frequent, superficial tool errors: schema mismatches, hallucinated parameters, and timeouts without fallbacks. These can be prevented through pre-validation. The lower left covers infrequent but troublesome infinite loops: the reflection chain has no termination condition, and the Plan keeps changing back and forth. Hard stop conditions must be established. The lower right covers more difficult hallucinations: inventing tools, inventing results, and even pretending to succeed. These can only be addressed through Grounding, connecting every step to a real data source. The upper right covers hidden cost overruns: token drift, repeated retrievals, and nested chains. Measurement and caps are essential. The key to contingency planning is to prepare by category, not fight fires afterward.

---

# 11_roadmap

Bring these elements together into an executable 12-week rollout plan. Phase 1 covers the first three weeks: get a minimum viable prototype working and reach a gold-standard case pass rate above 80% before moving on. Phase 2 runs from Weeks 4 to 7: expand the evaluation set to more than 100 items, turn on automated regression checks, and implement all retry and degradation mechanisms. Phase 3 covers Weeks 8 to 10: scale up, add caching and rate limiting, isolate tenants, and introduce tiered model routing. Phase 4 runs from Weeks 11 to 12: launch gradually, moving from 1% to 10% and then to full traffic, while monitoring the SLO so the flywheel can truly start turning. Every phase needs hard “pass” criteria; otherwise, you are merely rushing to hit a schedule.

---

# 12_cta_closing

One final summary. Agent engineering is not simply adding an LLM to a system and calling it done. It means truly embedding the LLM in an engineering system with architecture, context, evaluation, and observability. Only when all four are addressed can an Agent move from demo to production. I hope the framework I shared today can help you on your journey. Thank you, everyone.
