"""
LLM Output Evaluator — uses Groq/Llama to score its own outputs.
This is the "LLM-as-judge" pattern used in production RAG evaluation.

Metrics evaluated:
  - Faithfulness:   is the draft reply grounded in the KB context? (not hallucinated)
  - Relevance:      does the summary actually describe this ticket?
  - Completeness:   do the clarifying questions cover the key unknowns?
  - Tone:           is the draft reply professional and empathetic?

Each metric scored 1–5 with a reason.
"""

import os, json
import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"

EVAL_PROMPT = """You are a strict expert evaluator of AI-generated OSS issue triage responses.

You will be given:
- The original ticket (title + description)
- The KB context that was retrieved
- The AI-generated output (summary, clarifying questions, draft reply)

Score each dimension strictly from 1 to 5 using these rubrics:

FAITHFULNESS (Is the draft reply grounded ONLY in the KB context provided?):
  5 = Every claim in the reply is directly supported by the KB context
  4 = Mostly grounded, minor additions that are reasonable
  3 = Some claims not in KB but plausible
  2 = Several hallucinated claims not in KB
  1 = Reply ignores KB entirely or contradicts it

RELEVANCE (Does the summary accurately capture the core issue?):
  5 = Summary perfectly identifies root cause and impact
  4 = Summary accurate but misses one key detail
  3 = Summary partially correct, some inaccuracies
  2 = Summary vague or mostly off-topic
  1 = Summary completely wrong

COMPLETENESS (Do clarifying questions target the most critical unknowns?):
  5 = Questions are specific, targeted, and would unblock resolution
  4 = Good questions but missing one important angle
  3 = Questions are generic and could apply to any ticket
  2 = Questions are redundant or unhelpful
  1 = Questions are irrelevant to the issue

TONE (Is the draft reply appropriate for an OSS maintainer responding publicly?):
  5 = Professional, concise, empathetic, OSS-appropriate
  4 = Mostly appropriate, minor wordiness or formality issues
  3 = Acceptable but too formal/informal or slightly dismissive
  2 = Unprofessional or condescending
  1 = Inappropriate for public OSS communication

Be strict — most responses should score 3-4, not 5. Only give 5 if truly exceptional.
Compute overall as the average of the four scores rounded to 2 decimal places.

Return ONLY valid JSON — no markdown, no extra text, no explanation outside JSON:
{
  "faithfulness":   {"score": <integer 1-5>, "reason": "<one specific sentence citing evidence>"},
  "relevance":      {"score": <integer 1-5>, "reason": "<one specific sentence citing evidence>"},
  "completeness":   {"score": <integer 1-5>, "reason": "<one specific sentence citing evidence>"},
  "tone":           {"score": <integer 1-5>, "reason": "<one specific sentence citing evidence>"},
  "overall":        <float, average of four scores>,
  "improvement":    "<one concrete, actionable suggestion>"
}"""


async def evaluate_output(
    ticket_title:   str,
    ticket_desc:    str,
    kb_chunks:      list[dict],
    summary:        str,
    questions:      list[str],
    draft_reply:    str,
) -> dict:
    """Score LLM output across 4 dimensions using Llama-as-judge."""

    if not GROQ_API_KEY:
        return {"error": "GROQ_API_KEY not set — cannot run evaluation"}

    kb_context = "\n".join(f"- {c['text'][:200]}" for c in kb_chunks)

    user_msg = f"""Ticket Title: {ticket_title}
Ticket Description: {ticket_desc}

KB Context Retrieved:
{kb_context}

AI Output:
Summary: {summary}

Clarifying Questions:
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(questions))}

Draft Reply:
{draft_reply}"""

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": EVAL_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens":  600,
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
        return {"error": str(e)}