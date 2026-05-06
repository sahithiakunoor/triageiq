"""
Layer 2 — GenAI RAG Pipeline: Groq / Llama 3.3-70B
Prompt framing updated for OSS engineering issues (Apache, Spring, JBoss, CodeHaus).
"""

import os, json
import httpx
from data_pipeline import normalize_priority, PRIORITY_DISPLAY

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are an expert open source software maintainer helping triage engineering issues for projects like Apache Kafka, Apache Hadoop, Spring Framework, Spring Boot, Spring Security, and JBoss.

You receive a Jira issue (title + description), ML predictions (issue type + priority), extracted entities, and relevant knowledge base context retrieved from project documentation and runbooks.

Return a JSON object with exactly these keys:
{
  "summary": "1-2 sentence technical summary of the issue and its likely root cause or impact",
  "clarifying_questions": ["question 1", "question 2", "question 3"],
  "draft_reply": "A professional technical response a maintainer would write. Reference specific technical details from the issue. Ask for reproduction steps, stack trace, Java version, library version, and minimal reproducible example if not provided. Keep under 150 words.",
  "escalation_justification": "One sentence explaining why this priority level was assigned based on the technical impact."
}

Clarifying questions should be developer-focused:
- Exact Java version and OS
- Exact library/framework version where the issue occurs and last version where it worked
- Full stack trace if an exception is involved
- Minimal reproducible example or test case
- Whether this is a regression (worked in a previous version)

Return ONLY valid JSON — no markdown fences, no extra text."""


async def generate_assistance(
    ticket_text:  str,
    issue_type:   str,
    priority:     str,
    sla_risk:     float,
    entities:     dict,
    kb_results:   list[dict],
) -> dict:
    if GROQ_API_KEY:
        return await _groq_generate(ticket_text, issue_type, priority, entities, kb_results)
    return _template_assistant(ticket_text, issue_type, priority, entities, kb_results)


async def _groq_generate(ticket_text, issue_type, priority, entities, kb_results) -> dict:
    kb_context = "\n\n".join(
        f"[Source: {r['source']}]\n{r['text'][:300]}" for r in kb_results
    )
    norm    = normalize_priority(priority)
    display = PRIORITY_DISPLAY.get(norm, norm)

    user_msg = (
        f"Issue: {ticket_text}\n"
        f"Type: {issue_type}\n"
        f"Priority: {norm} ({display})\n"
        f"Entities: {json.dumps(entities)}\n\n"
        f"KB Context:\n{kb_context}"
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": 0.2,
        "max_tokens":  800,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload,
            )
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"[Groq error] {e}")
        return _template_assistant(ticket_text, issue_type, priority, entities, kb_results)


def _template_assistant(ticket_text, issue_type, priority, entities, kb_results) -> dict:
    norm    = normalize_priority(priority)
    display = PRIORITY_DISPLAY.get(norm, norm)
    context = " ".join(r["text"][:200] for r in kb_results)

    questions = [
        "What is the exact Java version and operating system you are using?",
        "What is the exact library/framework version where this occurs, and what was the last version where it worked?",
        "Can you provide a minimal reproducible example or failing test case?",
    ]
    if issue_type == "Bug":
        questions.append("Can you share the full stack trace if an exception is involved?")

    summary = (
        f"This {issue_type.lower()} is classified as {display} priority ({norm}). "
        f"Based on the description: {ticket_text[:200]}."
    )

    draft = (
        f"Thank you for reporting this issue.\n\n"
        f"To help us investigate this {issue_type.lower()}, could you please provide:\n"
        f"1. Exact Java version and OS\n"
        f"2. Exact version where the issue occurs and last version where it worked\n"
        f"3. A minimal reproducible example or failing test\n"
        f"4. Full stack trace if applicable\n\n"
        f"This has been triaged as {display} ({norm}) priority.\n\nThank you."
    )

    return {
        "summary":                  summary,
        "clarifying_questions":     questions,
        "draft_reply":              draft,
        "escalation_justification": f"Assigned {display} based on {issue_type} type and impact described.",
    }