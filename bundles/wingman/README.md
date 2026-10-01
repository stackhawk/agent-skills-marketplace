# StackHawk Wingman

Wingman installs the default StackHawk skill set in one plugin: HawkScan scanning, StackHawk platform reporting, seed data setup, and scan optimization. This folder is the Wingman bundle for GitHub Copilot CLI and Codex, which cannot install plugin dependencies. Its Copilot and Codex manifests load the four bundled skills `hawkscan`, `stackhawk-api`, `stackhawk-data-seed`, and `stackhawk-optimize` from `copilot-skills/`. Each skill comes from the same pinned `stackhawk/agent-skills` release as the individual plugins in this marketplace. Claude Code does not use this folder. It installs Wingman from `plugins/wingman/`, which brings in the four skills as dependent plugins.

The skills use the StackHawk `hawk` CLI and may connect to your StackHawk account. They can scan an application, query findings, or write configuration and seed artifacts in a repository when you invoke the relevant skill. Review each skill's instructions and the [StackHawk agent skills documentation](https://docs.stackhawk.com/ai-security/agent-skills/claude-code/) before use. [StackHawk support](https://docs.stackhawk.com/support/) can help with setup.

Wingman itself does not read or transmit `HAWK_API_KEY`. The bundled skills use the official `hawk` CLI, which authenticates with StackHawk's own platform using a StackHawk-issued key. Wingman is released under the MIT license.
