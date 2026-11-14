# Glama listing

Suggested name: **Industrial-AIOps Energy** (previous listing label: OT-AIops Energy).

Suggested profile description:

> Read-only substation and utility telemetry for AI agents: IEC 60870-5-104, DNP3
> and IEC 61850 MMS. Inspect point values and quality and pass normalized
> observations to Industrial-AIOps diagnostics. All MCP calls share the base
> audit and governance engine. Energy connectors expose no control-direction
> writes. Uses stdio; native-library requirements and verified device coverage
> vary by platform. Not a protection, control or certified safety system.

Suggested categories: **Energy**, **Monitoring** (use available Glama labels).

The root `glama.json` already includes maintainer `zw008`. Connect that account in
Glama after the default branch has synchronized. Include the same file when
creating every new public MCP service repository, preserving other maintainers.
This belongs at repository root, not inside each agent skill.

The server command is `iaiops-energy-mcp`; check `pyproject.toml` and the installation
instructions for native dependencies. The IEC 61850 wheel is Linux-specific and
DNP3 may require the documented patched build. A simple generic PyPI installation
must not be presented as verified for all three connectors. Do not reuse the base
server's `iaiops-mcp` command or require its profile selector for this standalone
energy server.

Update the Glama profile description and request a repository sync after merging.
The current repository release is 0.2.0; check the public listing for an older
cached README/version. A repository change does not establish that Glama has
refreshed its profile or successfully built a container.

See [official claim guidance](https://glama.ai/blog/2025-07-08-what-is-glamajson)
and the [maintainer schema](https://glama.ai/mcp/schemas/server.json).
