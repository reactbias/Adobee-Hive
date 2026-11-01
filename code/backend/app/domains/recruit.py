"""Recruiting domain: a company's agent searches people by a job posting, then asks their agents.

`hr.py` is the person card and the introduction. This is the part that fills the gap before it: a company has a
posting, not a list of names, and the people on the Hive have folders, not résumés in a database. Two tools:

- `hr_shortlist` reads the posting into requirements and searches every person card for them (`talent.py`). It
  touches published cards only, so it needs nobody's permission and returns nothing a card does not already say.
- `hr_interview` goes on from the shortlist (`interview.py`): the recruiter's agent asks each candidate's agent
  the posting's questions, the candidate's agent answers from its owner's folder — only if the owner's folder
  policy says yes, and only from files the folder link lets that recruiter read — and the candidates come back
  ranked on what was said. It introduces nobody; `hr_request_intro` is still the step that waits for a person.

Neither tool takes an approval argument. A candidate's yes comes from their own folder (`agent.md`), never from
the agent asking.
"""

from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from .. import guard, interview, services, talent
from .base import safe


def read_posting(job: str, expand: bool = False) -> talent.Job:
    """A posting as a Job. With `expand`, and only if a model is configured, the model adds related terms."""
    parsed = talent.parse_job(job)
    return talent.widen(parsed) if expand else parsed


def shortlist(job: str, limit: int = talent.DEFAULT_LIMIT, expand: bool = False) -> dict[str, Any]:
    """Read a posting and rank the person cards on this hub against it, with the evidence for each."""
    return talent.search(read_posting(job, expand), limit=limit)


def _over_budget(ctx: Context, expand: bool) -> str:
    """Why a call may not widen the posting with a model: the budget every model call on this hub spends."""
    if expand and services.enabled():
        return guard.admit_mcp(guard.llm_calls, ctx, charge_in_process=True)
    return ""


def register(server: MCPServer) -> None:
    """Add the recruiting tools to the Hive's MCP server."""

    @server.tool()
    def hr_shortlist(job: str, ctx: Context, limit: int = talent.DEFAULT_LIMIT, expand: bool = False) -> dict[str, Any]:
        """Find the people on this hub who fit a job posting. Paste the posting as text: a title, then requirements.

        The posting is split into requirements (a run like "AWS, Azure or GCP" is one requirement, not three), and
        each person card is read for them: `offers`, `skills`, headline, description and countersigned claims,
        never `needs`. `job` in the answer shows what was understood — check it. Every match carries, per
        requirement, how it was found (`literal`, `related`, `partial`, `similar`) and the person's own words, and
        every card left out says why. Public fields only: no contact details, and nothing is sent to anyone.

        `expand` asks the configured model, if there is one, to add related terms to each requirement; they are
        shown in `job` and only ever widen what counts, the matching and the scoring stay rules. It spends the
        same model budget as every other call that may reach a model.
        """
        if over := _over_budget(ctx, expand):
            return {"error": over}
        return safe(shortlist, job, limit, expand)

    @server.tool()
    def hr_interview(job: str, recruiter: str, ctx: Context, limit: int = 5, expand: bool = False) -> dict[str, Any]:
        """Shortlist for a posting, then have your agent question each candidate's agent, and rank on the answers.

        `recruiter` is your agent's name on this Hive (the other end of any folder link). A candidate is interviewed
        only if their own folder says `screening: yes`; one that says `ask` or says nothing gets a recorded request
        and stays `awaiting_consent`, ranked on the card alone and marked not interviewed; one that says `no` is
        left alone. What an answer quotes is limited to the files that candidate's folder lets you read, with the
        file named. Contact details are never part of it. Nobody is introduced: to meet someone, call
        `hr_request_intro` and wait for their yes. `expand` is as in `hr_shortlist`.
        """
        if over := _over_budget(ctx, expand):
            return {"error": over}
        return safe(lambda: interview.run(read_posting(job, expand), recruiter=recruiter, limit=limit))
