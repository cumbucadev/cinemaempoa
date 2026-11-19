"""The read-only catalog tools the conversational agent calls through the MCP
server in flask_backend/mcp_server.py: what is showing, where and when, and
what each cinema has shown. They only see published screenings
(`Screening.draft == False`) and raise CatalogToolError, with a pt-BR
message, when a call cannot be answered.
"""


class CatalogToolError(Exception):
    """A catalog tool call that cannot be answered. The message is in pt-BR
    and goes back to the agent."""
